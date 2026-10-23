#include "cpu_1d.hpp"
#include <vart/op_imp.h>

namespace {
struct MaxPool1d : vart::experimental::OpImpBase {
  MaxPool1d(const xir::Op* node, xir::Attrs* attrs) : OpImpBase(node, attrs) {
    asi_cpu::need(!node->get_attr<bool>("global") && node->get_attr<std::string>("pad_mode") == "FLOOR",
                  "maxpool1d plugin requires nonglobal FLOOR pooling");
    asi_cpu::need(node->get_attr<std::vector<int>>("kernel") == std::vector<int>({2}) &&
                 node->get_attr<std::vector<int>>("stride") == std::vector<int>({2}) &&
                 node->get_attr<std::vector<int>>("pad") == std::vector<int>({0,0}),
                 "maxpool1d plugin requires frozen ECG kernel=2,stride=2,pad=0,0");
    LOG(INFO) << "ASI_CPU_MAXPOOL1D_LOADED op=" << node->get_name();
  }
  int calculate(vart::simple_tensor_buffer_t<float> output,
                std::vector<vart::simple_tensor_buffer_t<float>> inputs) {
    try {
      asi_cpu::need(inputs.size() == 1, "maxpool1d expects one repeated input");
      asi_cpu::maxpool1d(output.data, inputs[0].data, inputs[0].tensor->get_shape(),
                        output.tensor->get_shape(), 2, 2);
      return 0;
    } catch (const std::exception& error) {
      LOG(ERROR) << "ASI_CPU_MAXPOOL1D_ERROR " << error.what();
      return 1;
    }
  }
};
}  // namespace
DEF_XIR_OP_IMP(MaxPool1d)
