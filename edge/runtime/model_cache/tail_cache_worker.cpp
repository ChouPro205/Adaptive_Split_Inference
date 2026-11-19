// Week 10 candidate: lazy cache of full-root GraphRunner contexts.
// Internal protocol only: four u32_le fields (op, job_id, split, byte_count).
// op 1 selects; op 2 executes FP32 NCL/NC input; clean EOF shuts down.
#include "../single_input/tail_io.hpp"
#include <chrono>
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
static double elapsed_ms(Clock::time_point start) {
  return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
}
static bool is_float(const xir::Tensor* t) {
  auto d=t->get_data_type(); return d.type==xir::DataType::FLOAT && d.bit_width==32;
}
static bool is_int8(const xir::Tensor* t) {
  auto d=t->get_data_type();
  return d.bit_width==8 && (d.type==xir::DataType::INT || d.type==xir::DataType::XINT);
}
using Runner = decltype(vitis::ai::GraphRunner::create_graph_runner(
    static_cast<xir::Graph*>(nullptr),static_cast<xir::Attrs*>(nullptr)));
struct Context {
  // Reverse destruction order: runner dies before attrs and graph.
  std::unique_ptr<xir::Graph> graph;
  std::unique_ptr<xir::Attrs> attrs;
  Runner runner;
  explicit Context(const std::string& path,int split) {
    graph=xir::Graph::deserialize(path); attrs=xir::Attrs::create();
    runner=vitis::ai::GraphRunner::create_graph_runner(graph.get(),attrs.get());
    require(bool(runner),"root GraphRunner creation failed");
    auto inputs=runner->get_inputs(), outputs=runner->get_outputs();
    require(inputs.size()==1 && outputs.size()==1,"one input/output required");
    auto in=inputs[0]->get_tensor(), out=outputs[0]->get_tensor();
    require(out->get_shape()==std::vector<int>({1,5}),"output must be (1,5)");
    require(is_float(in)||is_int8(in),"unsupported input dtype");
    require(is_float(out)||is_int8(out),"unsupported output dtype");
    if(is_int8(in)) require(in->has_attr("fix_point") && in->has_attr("round_mode") &&
      in->get_attr<std::string>("round_mode")=="DPU_ROUND","input quantization metadata missing");
    if(is_int8(out)) require(out->has_attr("fix_point"),"output fix_point missing");
    asi::Npy probe; probe.shape=asi::sample_shape(split);
    probe.shape.insert(probe.shape.begin(),1);
    size_t count=1; for(int d:probe.shape)count*=d; probe.values.resize(count);
    auto values=asi::input_sample(probe,split,0,in->get_shape());
    require(values.size()*(is_float(in)?4:1)==static_cast<size_t>(in->get_data_size()),"input byte count mismatch");
  }
  std::vector<float> infer(const asi::Npy& npy,int split) {
    auto inputs=runner->get_inputs(), outputs=runner->get_outputs();
    auto in=inputs[0]->get_tensor(), out=outputs[0]->get_tensor();
    auto values=asi::input_sample(npy,split,0,in->get_shape());
    size_t bytes=values.size()*(is_float(in)?4:1);
    std::vector<int8_t> q;
    if(is_int8(in)) {
      q.reserve(values.size());
      for(float x:values)q.push_back(asi::quantize(x,in->get_attr<int>("fix_point")));
      inputs[0]->copy_from_host(0,q.data(),bytes,0);
    } else inputs[0]->copy_from_host(0,values.data(),bytes,0);
    inputs[0]->sync_for_write(0,bytes);
    auto job=runner->execute_async(inputs,outputs); require(job.second==0,"execute_async failed");
    require(runner->wait(static_cast<int>(job.first),-1)==0,"wait failed");
    outputs[0]->sync_for_read(0,out->get_data_size());
    std::vector<float> logits(5);
    if(is_float(out))outputs[0]->copy_to_host(0,logits.data(),20,0);
    else {
      std::vector<int8_t> raw(5); outputs[0]->copy_to_host(0,raw.data(),5,0);
      for(int i=0;i<5;++i)logits[i]=std::ldexp(float(raw[i]),-out->get_attr<int>("fix_point"));
    }
    for(float x:logits)require(std::isfinite(x),"nonfinite output");
    return logits;
  }
};
int main(int argc,char** argv) {
  google::InitGoogleLogging(argv[0]); FLAGS_logtostderr=true;
  try {
    if(argc==2 && std::string(argv[1])=="--help") {
      std::cout << "asi-cache-worker MODEL_DIRECTORY\nInternal protocol: op/job/split/bytes u32_le; FP32 tensor for op=2.\n";
      return 0;
    }
    require(argc==2,"Usage: asi-cache-worker MODEL_DIRECTORY");
    const uint16_t endian=1;
    require(*reinterpret_cast<const uint8_t*>(&endian)==1 && sizeof(float)==4,"little-endian FP32 required");
    std::map<int,std::unique_ptr<Context>> cache;
    int selected=-1; uint32_t last_job=0;
    std::cout.precision(std::numeric_limits<double>::max_digits10);
    std::cout << "{\"event\":\"ready\",\"protocol\":1,\"execution\":\"root_graph\"}" << std::endl;
    while(true) {
      uint32_t header[4]; std::cin.read(reinterpret_cast<char*>(header),sizeof(header));
      if(std::cin.gcount()==0 && std::cin.eof())break;
      require(std::cin.gcount()==static_cast<std::streamsize>(sizeof(header)),"truncated header");
      const auto op=header[0], id=header[1], s=header[2], bytes=header[3];
      require(id>last_job && s<=10,"invalid job id or split"); last_job=id;
      if(op==1) {
        require(bytes==0,"select payload must be empty");
        auto start=Clock::now(); const bool hit=s<10 && cache.count(s);
        if(s<10 && !hit) {
          auto context=std::make_unique<Context>(std::string(argv[1])+"/tail_s"+std::to_string(s)+".xmodel",s);
          cache.emplace(s,std::move(context));
        }
        selected=static_cast<int>(s); const double select_ms=elapsed_ms(start);
        std::cout << "{\"event\":\"selected\",\"job_id\":" << id << ",\"split\":" << s
          << ",\"model_cache_hit\":" << (hit?"true":"false")
          << ",\"context_id\":" << (s<10?std::to_string(s+1):"null")
          << ",\"load_count\":" << (s<10?1:0)
          << ",\"contexts_count\":" << cache.size()
          << ",\"native_select_ms\":" << select_ms << "}" << std::endl;
      } else {
        require(op==2 && s<10 && selected==static_cast<int>(s) && cache.count(s),"select correct context before inference");
        asi::Npy npy; npy.shape=asi::sample_shape(s); npy.shape.insert(npy.shape.begin(),1);
        size_t count=1; for(int d:npy.shape)count*=d;
        require(bytes==count*4,"wrong tensor size"); npy.values.resize(count);
        std::cin.read(reinterpret_cast<char*>(npy.values.data()),bytes);
        require(bool(std::cin),"truncated tensor");
        for(float x:npy.values)require(std::isfinite(x),"nonfinite tensor");
        auto start=Clock::now(); auto logits=cache.at(s)->infer(npy,s); const double tail_ms=elapsed_ms(start);
        std::cout << "{\"event\":\"result\",\"job_id\":" << id << ",\"split\":" << s
          << ",\"logits\":" << asi::array(logits) << ",\"tail_ms\":" << tail_ms << "}" << std::endl;
      }
    }
    return 0;
  } catch(const std::exception& e) {
    std::cerr << "CACHE_WORKER_FAILED: " << e.what() << std::endl; return 1;
  }
}
