// Host-only ABI fixture: invoke the CPU plugin on a real model's op metadata.
// The tensor values are synthetic test fixtures, NOT inference/acceptance data.
#include "../runtime/tail_io.hpp"
#include <vart/op_imp.h>
#include <xir/graph/graph.hpp>
#include <dlfcn.h>
#include <iostream>
#include <memory>

struct Buffer : vart::TensorBuffer {
  explicit Buffer(const xir::Tensor* tensor) : TensorBuffer(tensor), values(tensor->get_element_num()) {}
  std::pair<uint64_t, size_t> data(const std::vector<int32_t> idx = {}) override {
    for (int x : idx) asi::require(x == 0, "fixture only supports zero offset");
    return {reinterpret_cast<uint64_t>(values.data()), values.size() * sizeof(float)};
  }
  std::vector<float> values;
};
int main(int argc, char** argv) {
  if (argc != 5) return 2;
  google::InitGoogleLogging(argv[0]);
  FLAGS_logtostderr = true;
  auto graph = xir::Graph::deserialize(argv[1]);
  const xir::Op* selected = nullptr;
  for (auto op : graph->get_ops())
    if (op->get_type() == argv[3]) { selected = op; break; }
  asi::require(selected != nullptr, "operator not found");
  std::string library = std::string(argv[2]) + "/libvart_op_imp_" + argv[3] + ".so";
  auto handle = dlopen(library.c_str(), RTLD_NOW | RTLD_LOCAL);
  if (!handle) { std::cerr << dlerror() << std::endl; return 1; }
  auto init = reinterpret_cast<vart_op_imp_t (*)(xir_op_t)>(dlsym(handle, "vart_init_op_imp"));
  asi::require(init != nullptr, "missing plugin entry point");
  auto implementation = init(const_cast<xir::Op*>(selected));
  auto attrs = xir::Attrs::create();
  void* state = implementation.init(const_cast<xir::Op*>(selected), attrs.get());
  auto input_ops = selected->get_input_ops("input");
  std::vector<std::unique_ptr<Buffer>> buffers;
  std::vector<vart_tensor_buffer_t> pointers;
  for (auto op : input_ops) {
    buffers.emplace_back(new Buffer(op->get_output_tensor()));
    for (size_t i = 0; i < buffers.back()->values.size(); ++i)
      buffers.back()->values[i] = 0.01f * static_cast<float>(static_cast<int>(i % 23) - 11);
    pointers.push_back(buffers.back().get());
  }
  Buffer output(selected->get_output_tensor());
  vart_op_imp_input_t inputs[] = {{"input", pointers.size(), pointers.data()}};
  int code = implementation.calculate(state, inputs, 1, &output);
  implementation.cleanup(state);
  asi::require(code == 0, "plugin calculation returned failure");
  std::ofstream file(argv[4]);
  file << "{\"scope\":\"CPU_OP_ABI_FIXTURE_ONLY\",\"type\":" << asi::quote(argv[3]) << ",\"inputs\":[";
  for (size_t i = 0; i < buffers.size(); ++i)
    file << (i ? "," : "") << "{\"shape\":" << asi::array(input_ops[i]->get_output_tensor()->get_shape())
         << ",\"values\":" << asi::array(buffers[i]->values) << "}";
  file << "],\"output_shape\":" << asi::array(selected->get_output_tensor()->get_shape())
       << ",\"output\":" << asi::array(output.values) << "}\n";
  return file ? 0 : 1;
}
