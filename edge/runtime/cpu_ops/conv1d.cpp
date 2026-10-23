#include "cpu_1d.hpp"
#include <vart/op_imp.h>
#include <iostream>

namespace {
struct Conv1d : vart::experimental::OpImpBase {
  Conv1d(const xir::Op* node, xir::Attrs* attrs) : OpImpBase(node, attrs) {
    asi_cpu::need(node->get_attr<int>("group") == 1 && node->get_attr<bool>("bias_term"),
                  "ECG conv1d plugin supports group=1 and bias_term=true only");
    asi_cpu::need(node->get_attr<std::string>("pad_mode") == "FLOOR", "unsupported conv1d pad_mode");
    kernel = node->get_attr<std::vector<int>>("kernel");
    stride = node->get_attr<std::vector<int>>("stride");
    dilation = node->get_attr<std::vector<int>>("dilation");
    pad = node->get_attr<std::vector<int>>("pad");
    asi_cpu::need(kernel == std::vector<int>({5}) && stride == std::vector<int>({1}) &&
                 dilation == std::vector<int>({1}) && pad == std::vector<int>({2,2}),
                 "conv1d plugin requires frozen ECG kernel=5,stride=1,dilation=1,pad=2,2");
    LOG(INFO) << "ASI_CPU_CONV1D_LOADED op=" << node->get_name();
  }
  int calculate(vart::simple_tensor_buffer_t<float> output,
                std::vector<vart::simple_tensor_buffer_t<float>> inputs) {
    try {
      asi_cpu::need(inputs.size() == 3, "conv1d expects repeated input=[activation,weight,bias]");
      auto in = inputs[0].tensor->get_shape(), weight = inputs[1].tensor->get_shape();
      auto out = output.tensor->get_shape();
      asi_cpu::need(weight.size() == 3 && weight[1] == kernel[0] &&
                   inputs[2].tensor->get_shape() == std::vector<int>({weight[0]}), "conv1d weight/bias shape mismatch");
      asi_cpu::conv1d(output.data, inputs[0].data, inputs[1].data, inputs[2].data,
                      in, weight, out, stride[0], dilation[0], pad[0], pad[1]);
      return 0;
    } catch (const std::exception& error) {
      LOG(ERROR) << "ASI_CPU_CONV1D_ERROR " << error.what();
      return 1;
    }
  }
  std::vector<int> kernel, stride, dilation, pad;
};
}  // namespace
DEF_XIR_OP_IMP(Conv1d)
