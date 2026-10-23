#pragma once
// Standalone input conversion for the frozen Week 3 ECG contract.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <limits>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace asi {
inline void require(bool ok, const std::string& message) {
  if (!ok) throw std::runtime_error(message);
}
struct Npy {
  std::vector<int> shape;
  std::vector<float> values;
};
inline std::vector<int> sample_shape(int split) {
  static const std::vector<std::vector<int>> shapes = {
      {1,360},{16,360},{16,180},{32,180},{32,90},
      {48,90},{48,45},{64,45},{64,22},{32}};
  require(split >= 0 && split < 10, "split must be 0..9");
  return shapes.at(split);
}
inline Npy load_npy(const std::string& path) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  require(bool(f), "cannot open NPY: " + path);
  auto size = f.tellg();
  require(size >= 10 && size <= 16 * 1024 * 1024, "invalid/oversized NPY");
  std::vector<unsigned char> bytes(static_cast<size_t>(size));
  f.seekg(0);
  f.read(reinterpret_cast<char*>(bytes.data()), bytes.size());
  require(bool(f), "incomplete NPY read");
  require(std::memcmp(bytes.data(), "\x93NUMPY", 6) == 0, "not a NPY file");
  unsigned major = bytes[6], minor = bytes[7];
  require((major == 1 || major == 2) && minor == 0, "only NPY 1.0/2.0 supported");
  size_t base = major == 1 ? 10 : 12;
  require(bytes.size() >= base, "truncated NPY header");
  size_t header_size = bytes[8] | (size_t(bytes[9]) << 8);
  if (major == 2) header_size |= size_t(bytes[10]) << 16 | size_t(bytes[11]) << 24;
  require(header_size <= 65536 && base + header_size <= bytes.size(), "bad NPY header length");
  std::string header(reinterpret_cast<char*>(bytes.data() + base), header_size);
  require(std::regex_search(header, std::regex("['\"]descr['\"]\\s*:\\s*['\"]<f4['\"]")), "NPY must be little-endian float32");
  require(std::regex_search(header, std::regex("['\"]fortran_order['\"]\\s*:\\s*False")), "NPY must be C-order");
  std::smatch match;
  require(std::regex_search(header, match, std::regex("['\"]shape['\"]\\s*:\\s*\\(([^)]*)\\)")), "missing NPY shape");
  std::istringstream dimensions(match[1].str());
  Npy result;
  std::string token;
  size_t count = 1;
  while (std::getline(dimensions, token, ',')) {
    if (token.find_first_not_of(" \t\r\n") == std::string::npos) continue;
    require(std::regex_match(token, std::regex("\\s*[0-9]+\\s*")), "invalid NPY dimension");
    auto n = std::stoull(token);
    require(n > 0 && n <= 100000 && count <= 4000000 / n, "NPY shape too large");
    result.shape.push_back(static_cast<int>(n));
    count *= n;
  }
  require(!result.shape.empty() && result.shape.size() <= 4, "invalid NPY rank");
  require(base + header_size + count * sizeof(float) == bytes.size(), "NPY size/shape mismatch");
  uint16_t endian = 1;
  require(*reinterpret_cast<unsigned char*>(&endian) == 1 && sizeof(float) == 4,
          "requires little-endian host with 32-bit float");
  result.values.resize(count);
  std::memcpy(result.values.data(), bytes.data() + base + header_size, count * sizeof(float));
  for (float x : result.values) require(std::isfinite(x), "NPY contains NaN/Inf");
  return result;
}
inline std::vector<float> input_sample(const Npy& npy, int split, int index,
                                     const std::vector<int>& target) {
  auto shape = sample_shape(split);
  auto expected = shape;
  expected.insert(expected.begin(), 1);
  require(npy.shape == expected, "golden must contain the one packet tensor with contract shape");
  require(index == 0, "sample index out of range");
  size_t count = npy.values.size();
  const float* source = npy.values.data() + index * count;
  auto ncl = shape;
  ncl.insert(ncl.begin(), 1);
  if (target == ncl) return {source, source + count};
  require(split < 9 && target == std::vector<int>({1, shape[1], shape[0]}),
          "runtime input shape is neither contract NCL/NC nor verified NLC; refusing reshape");
  std::vector<float> output(count);
  int channels = shape[0], length = shape[1];
  for (int c = 0; c < channels; ++c)
    for (int l = 0; l < length; ++l)
      output[l * channels + c] = source[c * length + l];
  return output;
}
inline int8_t quantize(float value, int fix_point) {
  require(fix_point >= -32 && fix_point <= 32, "unsupported fix_point");
  // Vitis AI 2.5 DPU_ROUND: nearest, half ties toward positive infinity.
  double scaled = std::ldexp(double(value), fix_point);
  require(std::isfinite(scaled), "nonfinite scaled input");
  return static_cast<int8_t>(std::max(-128.0, std::min(127.0, std::floor(scaled + 0.5))));
}
inline std::string quote(const std::string& value) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) {
      static const char* hex = "0123456789abcdef";
      out << "\\u00" << hex[c >> 4] << hex[c & 15];
    } else out << c;
  }
  out << '"';
  return out.str();
}
template <typename T> inline std::string array(const std::vector<T>& values) {
  std::ostringstream out;
  out.precision(std::numeric_limits<double>::max_digits10);
  out << '[';
  for (size_t i = 0; i < values.size(); ++i) out << (i ? "," : "") << +values[i];
  out << ']';
  return out.str();
}
}  // namespace asi
