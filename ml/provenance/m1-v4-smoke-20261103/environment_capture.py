import json, platform, subprocess, sys
import numpy, torch
q = subprocess.run(['nvidia-smi', '--query-gpu=name,compute_cap,driver_version,memory.total,memory.used',
                    '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout.strip().split(', ')
smi = subprocess.run(['nvidia-smi'], capture_output=True, text=True, check=True).stdout
cuda_driver = next((l.split('CUDA Version:')[1].split()[0] for l in smi.splitlines() if 'CUDA Version:' in l), None)
props = torch.cuda.get_device_properties(0)
print(json.dumps({
    'python': sys.version, 'python_executable': sys.executable, 'platform': platform.platform(),
    'numpy': numpy.__version__, 'torch': torch.__version__, 'torch_cuda_runtime': torch.version.cuda,
    'cudnn_version': torch.backends.cudnn.version(), 'cudnn_enabled': torch.backends.cudnn.enabled,
    'cuda_available': torch.cuda.is_available(), 'gpu_name_torch': torch.cuda.get_device_name(0),
    'compute_capability_torch': list(torch.cuda.get_device_capability(0)),
    'vram_total_bytes_torch': props.total_memory, 'multiprocessors': props.multi_processor_count,
    'nvidia_smi': {'name': q[0], 'compute_cap': q[1], 'driver_version': q[2], 'memory_total_MiB': int(q[3]),
                   'memory_used_MiB_at_capture': int(q[4]), 'cuda_version_driver_supports': cuda_driver},
    'arch_list': torch.cuda.get_arch_list()}, indent=1))
