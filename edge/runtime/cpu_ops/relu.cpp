#include "cpu_1d.hpp"
#include <vart/op_imp.h>

namespace {
struct Relu : vart::experimental::OpImpBase {
  Relu(const xir::Op* node, xir::Attrs* attrs) : OpImpBase(node, attrs) {
    LOG(INFO) << "ASI_CPU_RELU_LOADED op=" << node->get_name();
  }
  int calculate(vart::simple_tensor_buffer_t<float> output,
                vart::simple_tensor_buffer_t<float> input) {
    if (output.tensor->get_shape() != input.tensor->get_shape()) {
      LOG(ERROR) << "ASI_CPU_RELU_ERROR input/output shape mismatch";
      return 1;
    }
    for (int i = 0; i < output.tensor->get_element_num(); ++i)
      output.data[i] = asi_cpu::relu(input.data[i]);
    return 0;
  }
};
}  // namespace
DEF_XIR_OP_IMP(Relu)
