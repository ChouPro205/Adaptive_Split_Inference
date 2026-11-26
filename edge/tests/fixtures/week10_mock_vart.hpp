// HOST-only ABI-shaped test double. This does not implement a DPU/model.
#pragma once
#include <algorithm>
#include <cassert>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>
namespace google { inline void InitGoogleLogging(const char*) {} }
inline bool FLAGS_logtostderr = false;
namespace xir {
struct DataType { enum Type { FLOAT, INT, XINT }; Type type=FLOAT; int bit_width=32; };
class Tensor {
  std::vector<int> shape_;
 public:
  explicit Tensor(std::vector<int> s):shape_(std::move(s)){}
  DataType get_data_type() const { return {}; }
  std::vector<int> get_shape() const { return shape_; }
  bool has_attr(const std::string&) const { return true; }
  template<class T> T get_attr(const std::string&) const { return T{}; }
  int get_data_size() const { int n=4; for(int d:shape_)n*=d; return n; }
};
class Attrs { public: static std::unique_ptr<Attrs> create(){return std::make_unique<Attrs>();} };
class Graph {
 public:
  int split;
  explicit Graph(int s):split(s){}
  static std::unique_ptr<Graph> deserialize(const std::string& p) {
    auto at=p.rfind("tail_s");
    if(at==std::string::npos)throw std::runtime_error("fake path missing split");
    return std::make_unique<Graph>(std::stoi(p.substr(at+6)));
  }
};
}
namespace vart {
class Buffer {
  xir::Tensor tensor_;
 public:
  std::vector<float> values;
  explicit Buffer(std::vector<int> s):tensor_(s),values(tensor_.get_data_size()/4){}
  const xir::Tensor* get_tensor() const{return &tensor_;}
  void copy_from_host(int,const void* p,size_t n,int){assert(n==values.size()*4);std::memcpy(values.data(),p,n);}
  void copy_to_host(int,void* p,size_t n,int){assert(n==values.size()*4);std::memcpy(p,values.data(),n);}
  void sync_for_write(int,size_t){}
  void sync_for_read(int,size_t){}
};
class RunnerExt {
  Buffer in_,out_;
 public:
  static std::vector<int> shape(int s) {
    static const std::vector<std::vector<int>> shapes={
      {1,1,360},{1,16,360},{1,180,16},{1,32,180},{1,32,90},
      {1,48,90},{1,48,45},{1,64,45},{1,64,22},{1,32}};
    return shapes.at(s);
  }
  explicit RunnerExt(int s):in_(shape(s)),out_({1,5}){}
  std::vector<Buffer*> get_inputs(){return {&in_};}
  std::vector<Buffer*> get_outputs(){return {&out_};}
  std::pair<unsigned,int> execute_async(const std::vector<Buffer*>&,const std::vector<Buffer*>&){
    // Deliberately simple, depends on input. Never treated as real logits.
    std::copy_n(in_.values.begin(),5,out_.values.begin());return {1,0};
  }
  int wait(int,int){return 0;}
};
}
namespace vitis { namespace ai {
class GraphRunner {
 public:
  static std::unique_ptr<vart::RunnerExt> create_graph_runner(xir::Graph* g,xir::Attrs*) {
    static std::map<int,int> loads;
    if(++loads[g->split]>1)throw std::runtime_error("HOST fake: same model loaded twice");
    return std::make_unique<vart::RunnerExt>(g->split);
  }
};
}}
