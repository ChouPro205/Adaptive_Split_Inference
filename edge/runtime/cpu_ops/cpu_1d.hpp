#pragma once
// Narrow CPU kernels for the conv1d/maxpool1d nodes in the frozen ECG graphs.
// Inputs and weights here are already float32 outputs of the graph's fix ops.
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace asi_cpu {
inline float relu(float value) { return value < 0.0f ? 0.0f : value; }
inline void need(bool condition, const char* reason) {
  if (!condition) throw std::runtime_error(reason);
}
inline void positive3(const std::vector<int>& shape) {
  need(shape.size() == 3 && shape[0] > 0 && shape[1] > 0 && shape[2] > 0,
       "expected positive NLC/OKI rank-3 tensor");
}
inline void conv1d(float* output, const float* input, const float* weights,
                   const float* bias, const std::vector<int>& in,
                   const std::vector<int>& weight, const std::vector<int>& out,
                   int stride, int dilation, int left, int right) {
  positive3(in); positive3(weight); positive3(out);
  need(output && input && weights && bias, "null conv1d buffer");
  need(stride > 0 && dilation > 0 && left >= 0 && right >= 0, "invalid conv1d attributes");
  need(in[0] == out[0] && weight[0] == out[2] && weight[2] == in[2], "conv1d channel/batch mismatch");
  int extent = dilation * (weight[1] - 1) + 1;
  need(in[1] + left + right >= extent &&
       out[1] == (in[1] + left + right - extent) / stride + 1, "conv1d output length mismatch");
  for (int n = 0; n < out[0]; ++n)
    for (int l = 0; l < out[1]; ++l)
      for (int o = 0; o < out[2]; ++o) {
        float sum = bias[o];
        for (int k = 0; k < weight[1]; ++k) {
          int position = l * stride - left + k * dilation;
          if (position < 0 || position >= in[1]) continue;
          for (int c = 0; c < in[2]; ++c)
            sum += input[(n * in[1] + position) * in[2] + c] * weights[(o * weight[1] + k) * weight[2] + c];
        }
        output[(n * out[1] + l) * out[2] + o] = sum;
      }
}
inline void maxpool1d(float* output, const float* input, const std::vector<int>& in,
                      const std::vector<int>& out, int kernel, int stride) {
  positive3(in); positive3(out);
  need(output && input && kernel > 0 && stride > 0, "invalid maxpool1d input");
  need(in[0] == out[0] && in[2] == out[2] && in[1] >= kernel &&
       out[1] == (in[1] - kernel) / stride + 1, "maxpool1d shape mismatch");
  for (int n = 0; n < out[0]; ++n)
    for (int l = 0; l < out[1]; ++l)
      for (int c = 0; c < out[2]; ++c) {
        float value = -std::numeric_limits<float>::infinity();
        for (int k = 0; k < kernel; ++k)
          value = std::max(value, input[(n * in[1] + l * stride + k) * in[2] + c]);
        output[(n * out[1] + l) * out[2] + c] = value;
      }
}
}  // namespace asi_cpu
