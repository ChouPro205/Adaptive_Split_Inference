// Full-root GraphRunner for the frozen ECG tails; no child-DPU shortcut.
#include "tail_io.hpp"
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
namespace fs = std::filesystem;

static int fix_point(const xir::Tensor* tensor) {
  require(tensor->has_attr("fix_point"), "INT8 tensor has no fix_point");
  return tensor->get_attr<int>("fix_point");
}
static bool is_int8(const xir::Tensor* tensor) {
  auto type = tensor->get_data_type();
  return type.bit_width == 8 && (type.type == xir::DataType::XINT || type.type == xir::DataType::INT);
}
static bool is_float(const xir::Tensor* tensor) {
  auto type = tensor->get_data_type();
  return type.type == xir::DataType::FLOAT && type.bit_width == 32;
}
static std::string metadata(const xir::Tensor* tensor) {
  return "{\"name\":" + asi::quote(tensor->get_name()) + ",\"shape\":" +
         asi::array(tensor->get_shape()) + ",\"dtype\":" +
         asi::quote(tensor->get_data_type().to_string()) + ",\"fix_point\":" +
         (is_int8(tensor) ? std::to_string(fix_point(tensor)) : "null") + "}";
}
int main(int argc, char** argv) {
  google::InitGoogleLogging(argv[0]);
  FLAGS_logtostderr = true;
  try {
    std::map<std::string, std::string> options;
    for (int i = 1; i < argc; ++i) {
      std::string key = argv[i];
      if (key == "--help") {
        std::cout << "asi-tail-runner --model FILE.xmodel --input z_sN.npy --split N "
                     "--samples 1..20 --output NEW.json\n"
                     "Reads the first N frozen samples, fixed batch 1; creates root GraphRunner once.\n"
                     "--inspect-input FILE.npy validates NPY only; never executes a graph.\n";
        return 0;
      }
      require(i + 1 < argc, "missing value for " + key);
      require(options.emplace(key, argv[++i]).second, "duplicate option " + key);
    }
    if (options.count("--inspect-input")) {
      require(options.size() == 1, "inspect-input must be used alone");
      auto npy = asi::load_npy(options.at("--inspect-input"));
      std::cout << "{\"shape\":" << asi::array(npy.shape) << ",\"elements\":"
                << npy.values.size() << ",\"scope\":\"NPY_ONLY_NOT_INFERENCE\"}\n";
      return 0;
    }
    const std::vector<std::string> keys = {"--model", "--input", "--split", "--samples", "--output"};
    require(options.size() == keys.size(), "use --help for required options");
    for (const auto& key : keys) require(options.count(key), "missing option " + key);
    require(std::regex_match(options.at("--split"), std::regex("[0-9]")), "split must be 0..9");
    require(std::regex_match(options.at("--samples"), std::regex("[0-9]+")), "invalid samples");
    int split = std::stoi(options.at("--split")), samples = std::stoi(options.at("--samples"));
    require(samples >= 1 && samples <= 20, "samples must be 1..20");
    fs::path output = options.at("--output");
    require(!fs::exists(output) && !fs::exists(output.string() + ".partial"), "output already exists");
    auto npy = asi::load_npy(options.at("--input"));
    auto shape = asi::sample_shape(split);
    shape.insert(shape.begin(), 20);
    require(npy.shape == shape, "input differs from frozen 20-sample contract");
    std::cout << "STAGE=deserialize ROOT_GRAPH model=" << options.at("--model") << std::endl;
    auto graph = xir::Graph::deserialize(options.at("--model"));
    auto attrs = xir::Attrs::create();
    std::cout << "STAGE=create_root_GraphRunner" << std::endl;
    auto runner = vitis::ai::GraphRunner::create_graph_runner(graph.get(), attrs.get());
    require(bool(runner), "root GraphRunner creation failed");
    auto inputs = runner->get_inputs(), outputs = runner->get_outputs();
    require(inputs.size() == 1 && outputs.size() == 1, "expected one input and one final output");
    auto in = inputs[0]->get_tensor(), out = outputs[0]->get_tensor();
    require(out->get_shape() == std::vector<int>({1,5}), "final output must be (1,5)");
    require(is_float(in) || is_int8(in), "only FLOAT32 or signed INT8 runtime input supported");
    require(is_float(out) || is_int8(out), "only FLOAT32 or signed INT8 final output supported");
    if (is_int8(in)) {
      require(in->has_attr("round_mode") && in->get_attr<std::string>("round_mode") == "DPU_ROUND",
              "INT8 input needs explicit supported DPU_ROUND metadata");
    }
    std::cout << "INPUT=" << metadata(in) << "\nOUTPUT=" << metadata(out) << std::endl;
    std::ofstream report(output.string() + ".partial");
    require(bool(report), "cannot write output");
    report.precision(std::numeric_limits<double>::max_digits10);
    report << "{\"schema_version\":1,\"execution\":\"root_graph\",\"split\":" << split
           << ",\"input_tensor\":" << metadata(in) << ",\"output_tensor\":" << metadata(out)
           << ",\"quantization_rounding\":\"DPU_ROUND_HALF_TO_POSITIVE_INFINITY\",\"samples\":[";
    for (int index = 0; index < samples; ++index) {
      auto values = asi::input_sample(npy, split, index, in->get_shape());
      size_t input_bytes = values.size() * (is_float(in) ? sizeof(float) : 1);
      require(input_bytes == static_cast<size_t>(in->get_data_size()), "input byte count mismatch");
      std::vector<int8_t> quantized;
      if (is_int8(in)) {
        for (float x : values) quantized.push_back(asi::quantize(x, fix_point(in)));
        inputs[0]->copy_from_host(0, quantized.data(), input_bytes, 0);
      } else inputs[0]->copy_from_host(0, values.data(), input_bytes, 0);
      inputs[0]->sync_for_write(0, input_bytes);
      std::cout << "STAGE=execute_root_graph split=" << split << " sample=" << index << std::endl;
      auto job = runner->execute_async(inputs, outputs);
      require(job.second == 0, "execute_async returned an error");
      require(runner->wait(static_cast<int>(job.first), -1) == 0, "GraphRunner wait failed");
      outputs[0]->sync_for_read(0, out->get_data_size());
      std::vector<float> logits(5);
      std::vector<int8_t> raw(5);
      if (is_float(out)) outputs[0]->copy_to_host(0, logits.data(), logits.size() * sizeof(float), 0);
      else {
        outputs[0]->copy_to_host(0, raw.data(), raw.size(), 0);
        for (size_t j = 0; j < 5; ++j) logits[j] = std::ldexp(float(raw[j]), -fix_point(out));
      }
      for (float value : logits) require(std::isfinite(value), "final logits contain NaN/Inf");
      report << (index ? "," : "") << "{\"sample_index\":" << index
             << ",\"shape\":[1,5],\"logits\":" << asi::array(logits)
             << ",\"raw_int8\":" << (is_int8(out) ? asi::array(raw) : "null") << "}";
      report.flush();
      require(bool(report), "output write failed");
      std::cout << "FINAL_LOGITS=" << asi::array(logits) << std::endl;
    }
    report << "],\"status\":\"FULL_TAIL_EXECUTED_NOT_NUMERICALLY_ACCEPTED\"}\n";
    report.close();
    require(!report.fail(), "cannot close output");
    fs::rename(output.string() + ".partial", output);
    std::cout << "FULL_TAIL_EXECUTED samples=" << samples << std::endl;
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "BLOCKED_RUNTIME_OR_INPUT: " << error.what() << std::endl;
    return 1;
  }
}
