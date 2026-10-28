// Week 8: one root GraphRunner for s2; stdin u32_le byte count + NCL float32.
#include "../single_input/tail_io.hpp"
#include <chrono>
#include <iostream>
#include <memory>
#include <glog/logging.h>
#include <vitis/ai/graph_runner.hpp>
#include <xir/graph/graph.hpp>
#include <xir/attrs/attrs.hpp>
using asi::require;
static bool is_float(const xir::Tensor* t) {
  auto d=t->get_data_type(); return d.type==xir::DataType::FLOAT && d.bit_width==32;
}
static bool is_int8(const xir::Tensor* t) {
  auto d=t->get_data_type(); return d.bit_width==8 && (d.type==xir::DataType::INT || d.type==xir::DataType::XINT);
}
int main(int argc,char** argv) {
  google::InitGoogleLogging(argv[0]); FLAGS_logtostderr=true;
  try {
    require(argc==2,"Usage: asi-tail-worker tail_s2.xmodel");
    const uint16_t endian=1;
    require(*reinterpret_cast<const uint8_t*>(&endian)==1,"little-endian host required");
    auto graph=xir::Graph::deserialize(argv[1]); auto attrs=xir::Attrs::create();
    auto runner=vitis::ai::GraphRunner::create_graph_runner(graph.get(),attrs.get());
    require(bool(runner),"root GraphRunner creation failed");
    auto inputs=runner->get_inputs(),outputs=runner->get_outputs();
    require(inputs.size()==1 && outputs.size()==1,"one input/output required");
    auto in=inputs[0]->get_tensor(),out=outputs[0]->get_tensor();
    require(out->get_shape()==std::vector<int>({1,5}),"output must be (1,5)");
    require(is_float(in)||is_int8(in),"unsupported input dtype");
    require(is_float(out)||is_int8(out),"unsupported output dtype");
    if(is_int8(in)) require(in->has_attr("fix_point") && in->has_attr("round_mode") &&
      in->get_attr<std::string>("round_mode")=="DPU_ROUND","missing input quantization metadata");
    if(is_int8(out)) require(out->has_attr("fix_point"),"missing output fix_point");
    // Exercise the same NCL/NLC input validation as the saved single-input runner.
    asi::Npy npy; npy.shape={1,16,180}; npy.values.resize(2880);
    (void)asi::input_sample(npy,2,0,in->get_shape());
    std::cout.precision(std::numeric_limits<float>::max_digits10);
    std::cout << "{\"ready\":true,\"split\":2,\"execution\":\"root_graph\"}" << std::endl;
    while(true) {
      uint32_t bytes=0; std::cin.read(reinterpret_cast<char*>(&bytes),4);
      if(std::cin.gcount()==0 && std::cin.eof()) break;
      require(std::cin.gcount()==4 && bytes==2880*4,"invalid worker frame length");
      std::cin.read(reinterpret_cast<char*>(npy.values.data()),bytes);
      require(bool(std::cin),"truncated worker input");
      for(float x:npy.values) require(std::isfinite(x),"nonfinite input");
      const auto start=std::chrono::steady_clock::now();
      auto values=asi::input_sample(npy,2,0,in->get_shape());
      const auto count=values.size()*(is_float(in)?sizeof(float):1);
      require(count==static_cast<size_t>(in->get_data_size()),"input byte count mismatch");
      std::vector<int8_t> q;
      if(is_int8(in)) {
        for(float x:values) q.push_back(asi::quantize(x,in->get_attr<int>("fix_point")));
        inputs[0]->copy_from_host(0,q.data(),count,0);
      } else inputs[0]->copy_from_host(0,values.data(),count,0);
      inputs[0]->sync_for_write(0,count);
      auto job=runner->execute_async(inputs,outputs); require(job.second==0,"execute_async failed");
      require(runner->wait(static_cast<int>(job.first),-1)==0,"wait failed");
      outputs[0]->sync_for_read(0,out->get_data_size()); std::vector<float> logits(5);
      if(is_float(out)) outputs[0]->copy_to_host(0,logits.data(),20,0);
      else {
        std::vector<int8_t> raw(5); outputs[0]->copy_to_host(0,raw.data(),5,0);
        for(int i=0;i<5;++i) logits[i]=std::ldexp(float(raw[i]),-out->get_attr<int>("fix_point"));
      }
      for(float x:logits) require(std::isfinite(x),"nonfinite output");
      double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
      std::cout << "{\"logits\":" << asi::array(logits) << ",\"tail_ms\":" << ms << "}" << std::endl;
    }
    return 0;
  } catch(const std::exception& e) { std::cerr << "WORKER_FAILED: " << e.what() << std::endl; return 1; }
}
