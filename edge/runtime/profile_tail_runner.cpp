// Profile the complete frozen ECG root graph; reuse existing input conversion.
#include "tail_io.hpp"
#include <chrono>
#include <filesystem>
#include <iostream>
#include <map>
#include <memory>
#include <glog/logging.h>
#include <vitis/ai/graph_runner.hpp>
#include <xir/graph/graph.hpp>
#include <xir/attrs/attrs.hpp>
#include <xir/tensor/tensor.hpp>

using asi::require;
using Clock = std::chrono::steady_clock;
namespace fs = std::filesystem;
static double ms(Clock::time_point a, Clock::time_point b) {
  return std::chrono::duration<double, std::milli>(b - a).count();
}
static bool int8(const xir::Tensor* t) {
  auto d = t->get_data_type();
  return d.bit_width == 8 && (d.type == xir::DataType::XINT || d.type == xir::DataType::INT);
}
static bool fp32(const xir::Tensor* t) {
  auto d = t->get_data_type();
  return d.bit_width == 32 && d.type == xir::DataType::FLOAT;
}
static int fix(const xir::Tensor* t) {
  require(t->has_attr("fix_point"), "missing fix_point");
  return t->get_attr<int>("fix_point");
}
static std::string tensor_json(const xir::Tensor* t) {
  return "{\"name\":" + asi::quote(t->get_name()) + ",\"shape\":" + asi::array(t->get_shape()) +
         ",\"dtype\":" + asi::quote(t->get_data_type().to_string()) + "}";
}
struct Record {
  int sample;
  double prepare, input, execute, output, total;
  std::vector<float> logits;
};
static void write_record(std::ostream& out, const Record& r) {
  out << "{\"sample_index\":" << r.sample << ",\"prepare_ms\":" << r.prepare
      << ",\"input_sync_ms\":" << r.input << ",\"execute_wait_ms\":" << r.execute
      << ",\"output_read_ms\":" << r.output << ",\"tail_total_ms\":" << r.total
      << ",\"logits\":" << asi::array(r.logits) << "}";
}
int main(int argc, char** argv) {
  google::InitGoogleLogging(argv[0]);
  FLAGS_logtostderr = true;
  try {
    std::map<std::string, std::string> opt;
    for (int i = 1; i < argc; ++i) {
      std::string key = argv[i];
      if (key == "--help") {
        std::cout << "asi-tail-profiler --model FILE --input FROZEN.npy --split 0..9 "
                     "--warmup N --repeats N --output NEW.json\n"
                     "steady_clock on board; root CPU+DPU graph; NOT DPU-only timing.\n";
        return 0;
      }
      require(i + 1 < argc, "missing option value");
      require(opt.emplace(key, argv[++i]).second, "duplicate option");
    }
    for (auto key : {"--model", "--input", "--split", "--warmup", "--repeats", "--output"})
      require(opt.count(key), std::string("missing ") + key);
    require(opt.size() == 6, "unknown option");
    auto number = [&](const std::string& key, int lo, int hi) {
      require(std::regex_match(opt.at(key), std::regex("[0-9]+")), "invalid " + key);
      int n = std::stoi(opt.at(key));
      require(n >= lo && n <= hi, "out of range " + key);
      return n;
    };
    int split = number("--split", 0, 9);
    int warmup = number("--warmup", 0, 100000);
    int repeats = number("--repeats", 1, 100000);
    fs::path path = opt.at("--output");
    require(!fs::exists(path) && !fs::exists(path.string() + ".partial"), "output exists");
    auto npy = asi::load_npy(opt.at("--input"));
    auto shape = asi::sample_shape(split);
    shape.insert(shape.begin(), 20);
    require(npy.shape == shape, "not the frozen 20-sample input");
    std::ofstream report(path.string() + ".partial");
    require(bool(report), "cannot open output");
    report.precision(std::numeric_limits<double>::max_digits10);
    auto t0 = Clock::now();
    auto graph = xir::Graph::deserialize(opt.at("--model"));
    auto t1 = Clock::now();
    auto attrs = xir::Attrs::create();
    auto runner = vitis::ai::GraphRunner::create_graph_runner(graph.get(), attrs.get());
    require(bool(runner), "root GraphRunner creation failed");
    auto t2 = Clock::now();
    auto inputs = runner->get_inputs(), outputs = runner->get_outputs();
    require(inputs.size() == 1 && outputs.size() == 1, "expected one input/output");
    auto in = inputs[0]->get_tensor(), out = outputs[0]->get_tensor();
    require(out->get_shape() == std::vector<int>({1, 5}), "not final logits (1,5)");
    require(fp32(in) || int8(in), "unsupported input dtype");
    require(fp32(out) || int8(out), "unsupported output dtype");
    if (int8(in)) require(in->has_attr("round_mode") &&
        in->get_attr<std::string>("round_mode") == "DPU_ROUND", "unsupported rounding");
    auto t3 = Clock::now();
    auto run = [&](int sample) {
      Record r{};
      r.sample = sample;
      auto a = Clock::now();
      auto values = asi::input_sample(npy, split, sample, in->get_shape());
      std::vector<int8_t> q;
      if (int8(in)) {
        q.reserve(values.size());
        for (float x : values) q.push_back(asi::quantize(x, fix(in)));
      }
      size_t bytes = values.size() * (fp32(in) ? sizeof(float) : 1);
      require(bytes == static_cast<size_t>(in->get_data_size()), "input byte mismatch");
      auto b = Clock::now();
      if (int8(in)) inputs[0]->copy_from_host(0, q.data(), bytes, 0);
      else inputs[0]->copy_from_host(0, values.data(), bytes, 0);
      inputs[0]->sync_for_write(0, bytes);
      auto c = Clock::now();
      auto job = runner->execute_async(inputs, outputs);
      require(job.second == 0, "execute_async failed");
      require(runner->wait(static_cast<int>(job.first), -1) == 0, "wait failed");
      auto d = Clock::now();
      outputs[0]->sync_for_read(0, out->get_data_size());
      r.logits.resize(5);
      if (fp32(out)) outputs[0]->copy_to_host(0, r.logits.data(), 5 * sizeof(float), 0);
      else {
        std::vector<int8_t> raw(5);
        outputs[0]->copy_to_host(0, raw.data(), raw.size(), 0);
        for (int j = 0; j < 5; ++j) r.logits[j] = std::ldexp(float(raw[j]), -fix(out));
      }
      for (float x : r.logits) require(std::isfinite(x), "nonfinite logits");
      auto e = Clock::now();
      r.prepare = ms(a, b); r.input = ms(b, c); r.execute = ms(c, d);
      r.output = ms(d, e); r.total = ms(a, e);
      return r;
    };
    auto first = run(0);
    for (int i = 0; i < warmup; ++i) run(i % 20);
    std::vector<Record> records;
    records.reserve(repeats);
    for (int i = 0; i < repeats; ++i) records.push_back(run(i % 20));
    report << "{\"schema_version\":1,\"execution\":\"root_graph\",\"clock\":\"std::chrono::steady_clock\","
           << "\"split\":" << split << ",\"warmup\":" << warmup << ",\"repeats\":" << repeats
           << ",\"deserialize_ms\":" << ms(t0, t1) << ",\"create_runner_ms\":" << ms(t1, t2)
           << ",\"tensor_setup_ms\":" << ms(t2, t3) << ",\"model_load_ms\":" << ms(t0, t3)
           << ",\"input_tensor\":" << tensor_json(in) << ",\"output_tensor\":" << tensor_json(out)
           << ",\"first_inference\":";
    write_record(report, first);
    report << ",\"measurements\":[";
    for (size_t i = 0; i < records.size(); ++i) {
      if (i) report << ',';
      write_record(report, records[i]);
    }
    report << "],\"status\":\"PROFILE_EXECUTED_NUMERIC_ACCEPTANCE_SEPARATE\"}\n";
    report.close();
    require(!report.fail(), "cannot finish report");
    fs::rename(path.string() + ".partial", path);
    std::cout << "PROFILE_EXECUTED split=" << split << " repeats=" << repeats << '\n';
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "PROFILE_BLOCKED: " << e.what() << '\n';
    return 1;
  }
}
