#!/usr/bin/env bash
# ==============================================================================
# compile_all_splits.sh
# 
# Vai tro: SV2 (FPGA / Edge) - Tuan 4
# Du an : Adaptive Split Inference
# Muc tieu:
#   - Tu dong hoa quy trinh luong tu hoa (vai_q_onnx) va bien dich (vai_c_xir)
#     cho 10 mo hinh ONNX tail tu diem cat s=0 den s=9.
#   - Luu tru toan bo ket qua build va log vao thu muc noi bo edge/build/
#   - Bat loi tung buoc rieng biet cho tung s, khong dung set -e, chay qua dem.
#   - Xuat file tong ket edge/build/summary.txt.
# ==============================================================================

# Bat loi bien chua khai bao, KHONG dung set -e de tu xu ly loi tung buoc bang if
set -u

# Xac dinh thu muc goc cua repository va thu muc edge
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Khai bao checkpoint PyTorch va DPU architecture
checkpoint_file="${REPO_ROOT}/ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/model/checkpoint.pt"
arch_file="/opt/vitis_ai/compiler/arch/DPUCZDX8G/KV260/arch.json"

# Quy uoc cau truc thu muc output noi bo cua edge (nam trong edge/build/)
out_build_dir="${REPO_ROOT}/edge/build"
out_quantized_dir="${out_build_dir}/quantized"
out_compiled_dir="${out_build_dir}/compiled"
out_logs_dir="${out_build_dir}/logs"
summary_file="${out_build_dir}/summary.txt"

# Tao cac thu muc output neu chua ton tai
mkdir -p "${out_quantized_dir}"
mkdir -p "${out_compiled_dir}"
mkdir -p "${out_logs_dir}"

# Khoi tao bien dem so luong (dung hau to _count theo quy uoc 5.3)
success_count=0
fail_count=0

# Xoa hoac tao moi file summary cho phien chay hien tai
> "${summary_file}"

echo "======================================================================"
echo " Bat dau tu dong hoa quantize & compile 10 diem cat (s = 0 den 9)"
echo " Thu muc output: ${out_build_dir}"
echo "======================================================================"

# Lap qua cac diem cat tu 0 den 9
for s in {0..9}; do
    quantized_dir_s="${out_quantized_dir}/s${s}"
    compiled_out="${out_compiled_dir}/tail_s${s}.xmodel"
    log_file="${out_logs_dir}/log_s${s}.txt"

    echo ">>> Dang xu ly split s = ${s}..."

    # Tao thu muc rieng cho diem cat s
    mkdir -p "${quantized_dir_s}"

    # Khoi tao log rieng cho diem cat s
    echo "=== Bat dau xu ly s = ${s} vao luc $(date) ===" > "${log_file}"

    # Buoc 1a: Calibrate bang vai_q_pytorch (quantize_tail.py)
    echo "--- Buoc 1a: Chay calibration qua quantize_tail.py ---" >> "${log_file}"
    python "${SCRIPT_DIR}/quantize_tail.py" \
        -s "${s}" \
        --quant_mode calib \
        --output_dir "${quantized_dir_s}" \
        --checkpoint "${checkpoint_file}" >> "${log_file}" 2>&1

    calib_exit_code=$?
    if [ ${calib_exit_code} -ne 0 ]; then
        echo "Loi o buoc calibration vai_q_pytorch cho s = ${s} (exit code: ${calib_exit_code})" >> "${log_file}"
        echo "s=${s}: THAT_BAI (xem log_s${s}.txt)" >> "${summary_file}"
        fail_count=$((fail_count + 1))
        continue
    fi

    # Buoc 1b: Xuat file _int.xmodel bang vai_q_pytorch
    echo "--- Buoc 1b: Xuat file _int.xmodel qua quantize_tail.py ---" >> "${log_file}"
    python "${SCRIPT_DIR}/quantize_tail.py" \
        -s "${s}" \
        --quant_mode test \
        --output_dir "${quantized_dir_s}" \
        --checkpoint "${checkpoint_file}" >> "${log_file}" 2>&1

    test_exit_code=$?
    if [ ${test_exit_code} -ne 0 ]; then
        echo "Loi o buoc xuat XIR int xmodel cho s = ${s} (exit code: ${test_exit_code})" >> "${log_file}"
        echo "s=${s}: THAT_BAI (xem log_s${s}.txt)" >> "${summary_file}"
        fail_count=$((fail_count + 1))
        continue
    fi

    # Tim file xmodel trung gian
    int_xmodel="${quantized_dir_s}/Sequential_int.xmodel"
    if [ ! -f "${int_xmodel}" ]; then
        int_xmodel="${quantized_dir_s}/tail_${s}_int.xmodel"
    fi

    if [ ! -f "${int_xmodel}" ]; then
        echo "Loi: Khong tim thay file xmodel trung gian tai ${quantized_dir_s}" >> "${log_file}"
        echo "s=${s}: THAT_BAI (xem log_s${s}.txt)" >> "${summary_file}"
        fail_count=$((fail_count + 1))
        continue
    fi

    # Buoc 2: Bien dich bang vai_c_xir
    echo "--- Buoc 2: Chay vai_c_xir ---" >> "${log_file}"
    vai_c_xir \
        -x "${int_xmodel}" \
        -a "${arch_file}" \
        -o "${out_compiled_dir}" \
        -n "tail_s${s}" >> "${log_file}" 2>&1

    compile_exit_code=$?
    if [ ${compile_exit_code} -ne 0 ] || [ ! -f "${compiled_out}" ]; then
        echo "Loi o buoc compile vai_c_xir cho s = ${s} (exit code: ${compile_exit_code})" >> "${log_file}"
        echo "s=${s}: THAT_BAI (xem log_s${s}.txt)" >> "${summary_file}"
        fail_count=$((fail_count + 1))
    else
        echo "Hoan thanh thanh cong s = ${s}" >> "${log_file}"
        echo "s=${s}: THANH_CONG" >> "${summary_file}"
        success_count=$((success_count + 1))
    fi
done

# Tong ket qua trinh
echo "======================================================================"
echo "Qua trinh hoan tat!"
echo "Tong so diem cat THANH_CONG: ${success_count}"
echo "Tong so diem cat THAT_BAI: ${fail_count}"
echo "Chi tiet xem tai file: ${summary_file}"
echo "======================================================================"

# Ghi dong tong ket vao cuoi file summary
echo "Tong so diem cat THANH_CONG: ${success_count}" >> "${summary_file}"
echo "Tong so diem cat THAT_BAI: ${fail_count}" >> "${summary_file}"
