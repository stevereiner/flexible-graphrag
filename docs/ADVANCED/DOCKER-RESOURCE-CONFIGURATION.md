# Docker Resource Configuration Guide

Flexible GraphRAG runs a significant number of Docker containers simultaneously (Neo4j, Elasticsearch, Qdrant, GraphDB, Fuseki, Postgres, Kibana, and optionally vLLM). This guide covers how to allocate adequate memory and CPU resources on each platform.

---

## Windows (WSL2 Backend)

Docker Desktop on Windows runs all containers inside a WSL2 Linux VM. By default this VM is severely memory-limited.

### Default WSL2 Limits (Windows 11)

| Resource | Default | Impact |
|----------|---------|--------|
| Memory | `min(50% RAM, 8GB)` | **8GB** on a 128GB system — far too low |
| Processors | All logical CPUs | Fine — no change needed |
| Swap | 25% of memory | ~2GB — too small |

### Fix: Create `C:\Users\<YourUsername>\.wslconfig`

```ini
[wsl2]
# Memory for the WSL2 VM — all Docker containers share this pool.
# Rule of thumb: total RAM / 2, but leave at least 16GB for Windows.
# Examples:
#   16GB system  -> memory=8GB
#   32GB system  -> memory=16GB
#   64GB system  -> memory=32GB
#   128GB system -> memory=48GB  (leaves 80GB for Windows + native apps)
memory=48GB

# Swap — increase from the tiny default
swap=8GB

# Processors — WSL2 default is all logical CPUs, which is correct.
# Only set this if WSL2 is starving Windows processes.
# processors=24

[experimental]
# Return unused WSL2 memory to Windows when containers are idle.
# "gradual" reclaims slowly (safer); "dropcache" reclaims aggressively.
autoMemoryReclaim=gradual
```

Adjust `memory=` based on your system RAM:

| System RAM | Recommended `memory=` | Leaves for Windows |
|-----------|----------------------|-------------------|
| 16 GB | 8 GB | 8 GB |
| 32 GB | 16 GB | 16 GB |
| 64 GB | 32 GB | 32 GB |
| 128 GB | 32-48 GB | 80-96 GB |

> Rule of thumb: full stack needs ~16GB, add ~8GB for vLLM = **24GB minimum** for full stack + vLLM. Scale up on larger systems to leave headroom.

### Apply the Config

WSL2 only reads `.wslconfig` on VM startup. **Order matters:**

```powershell
# 1. Shut down the WSL2 VM
wsl --shutdown

# 2. Restart Docker Desktop
#    Right-click tray icon -> Restart
#    (or kill and relaunch Docker Desktop.exe)
```

### Verify

```powershell
# Check memory inside WSL2 — should show your configured amount
wsl -- free -h

# Check Docker Desktop is using the new limits
docker info | Select-String "Total Memory"
```

### Why Not Use Docker Desktop Resource Settings?

Docker Desktop's Settings → Resources sliders also control WSL2 memory — they write to `.wslconfig` under the hood. However, Docker Desktop may overwrite your `.wslconfig` on upgrade. Using the file directly is more reliable and survives Docker Desktop updates.

---

## macOS

Docker Desktop for Mac runs containers in a lightweight Linux VM (Apple Hypervisor on Apple Silicon, HyperKit on Intel). Default limits are more generous than Windows but still need tuning for the full stack.

### Default Docker Desktop Limits (macOS)

| Resource | Default |
|----------|---------|
| Memory | 8 GB |
| CPUs | 4 |
| Swap | 1 GB |

### Configure via Docker Desktop UI

Docker Desktop → Settings (gear icon) → Resources → Advanced:

| Setting | Recommendation | Notes |
|---------|---------------|-------|
| Memory | 50% of RAM | Min 16GB for full stack |
| CPUs | 75% of cores | Leave headroom for macOS |
| Swap | 4 GB | Increase from 1GB default |
| Disk image size | 100+ GB | Models + DB volumes add up |

**Apply**: Click "Apply & Restart"

### macOS-Specific Notes

- **Apple Silicon (M1/M2/M3/M4)**: vLLM does not have a native ARM Docker image. Use `LLM_PROVIDER=ollama` or a remote API provider instead. The `vllm/vllm-openai` image is x86/CUDA only.
- **Intel Mac**: vLLM Docker works if you have an NVIDIA eGPU, otherwise CPU-only inference is very slow — use a remote provider.
- **Memory pressure**: macOS aggressively uses RAM for disk cache. If Docker containers are being killed, reduce Docker's memory allocation slightly to let macOS breathe.

### Configure via `.wslconfig` equivalent (colima users)

If using [colima](https://github.com/abiosoft/colima) instead of Docker Desktop:

```bash
colima start --cpu 8 --memory 16 --disk 100
# or edit ~/.colima/default/colima.yaml
```

---

## Linux

Linux has two distinct Docker installation modes with very different resource behavior.

### Docker Desktop for Linux (VM-based)

Docker Desktop for Linux (available as a `.deb`/`.rpm` package) runs containers inside a VM using QEMU, identical to the macOS approach. It has the same default memory limits:

| Resource | Default |
|----------|---------|
| Memory | 8 GB |
| CPUs | 4 |
| Swap | 1 GB |

**Configure via Docker Desktop UI** — same as macOS:

Docker Desktop → Settings → Resources → Advanced:

| Setting | Recommendation | Notes |
|---------|---------------|-------|
| Memory | 50% of RAM | Min 16GB for full stack |
| CPUs | 75% of cores | Leave headroom for desktop apps |
| Swap | 4 GB | Increase from 1GB default |
| Disk image size | 100+ GB | Models + DB volumes add up |

**Apply**: Click "Apply & Restart"

### Docker Engine (native, no VM)

If using Docker Engine installed via `apt`/`dnf`/`pacman` (the CLI-only install, no Docker Desktop UI), containers run natively — no VM, no memory cap. Containers have direct access to all host RAM and CPUs. No resource configuration is needed.

### Things to Check

**1. cgroup memory limits** — some Linux distributions set conservative default cgroup limits:

```bash
# Check if memory limits are set
docker info | grep "Total Memory"

# Should match your system RAM (minus OS overhead)
free -h
```

**2. Swap** — ensure swap is configured if running large models:

```bash
# Check current swap
swapon --show

# Add 8GB swap file if needed
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**3. vm.max_map_count** — required for Elasticsearch:

```bash
# Check current value (needs to be >= 262144)
cat /proc/sys/vm/max_map_count

# Set temporarily
sudo sysctl -w vm.max_map_count=262144

# Set permanently
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

**4. NVIDIA GPU (for vLLM)** — install the NVIDIA Container Toolkit:

```bash
# Ubuntu/Debian
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify
docker run --rm --runtime nvidia --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

---

## Minimum Recommended Resources by Stack Size

### Minimal Stack (Neo4j + Qdrant + Elasticsearch)
| Platform | Memory | CPUs |
|----------|--------|------|
| Windows WSL2 | 8 GB | default |
| macOS Docker Desktop | 8 GB | 4 |
| Linux Docker Desktop | 8 GB | 4 |
| Linux Docker Engine | ~6 GB available | 4 |

### Full Stack (all databases + observability)
| Platform | Memory | CPUs |
|----------|--------|------|
| Windows WSL2 | 16 GB | default |
| macOS Docker Desktop | 16 GB | 8 |
| Linux Docker Desktop | 16 GB | 8 |
| Linux Docker Engine | ~12 GB available | 8 |

### Full Stack + vLLM (7B model)
| Platform | Memory | CPUs | GPU VRAM |
|----------|--------|------|----------|
| Windows WSL2 | ~24 GB | default | 16 GB+ |
| macOS Docker Desktop | N/A (use Ollama) | — | — |
| Linux Docker Desktop | ~24 GB | 75% of cores | 16 GB+ |
| Linux Docker Engine | native (no limit) | native | 16 GB+ |

### Full Stack + vLLM (14B model)
| Platform | Memory | CPUs | GPU VRAM |
|----------|--------|------|----------|
| Windows WSL2 | ~24 GB | default | 28 GB+ |
| Linux Docker Desktop | ~24 GB | 75% of cores | 28 GB+ |
| Linux Docker Engine | native (no limit) | native | 28 GB+ |

> **Note**: vLLM model weights load onto GPU VRAM. System RAM inside the Docker VM covers KV cache, activations, and the Python process — roughly 4-8GB on top of the full stack's ~12GB baseline. The WSL2 default of 8GB is too low for the full stack alone; 24GB comfortably covers full stack + vLLM.

---

## Troubleshooting

### Container keeps getting killed (OOM)
- **Windows**: `.wslconfig` `memory=` too low — increase it
- **macOS**: Docker Desktop memory slider too low — increase in Settings → Resources
- **Linux**: Check `dmesg | grep -i "oom"` to confirm OOM kill; add swap or free RAM

### Elasticsearch fails to start
```
max virtual memory areas vm.max_map_count [65530] is too low
```
Linux only — set `vm.max_map_count=262144` (see Linux section above). Not needed on Windows/macOS.

### vLLM extracts 0 entities on some chunks
Most likely memory pressure inside the WSL2/Docker VM. The KV cache gets evicted mid-generation, returning an empty response. Fix: increase `memory=` in `.wslconfig` (Windows) or Docker Desktop memory slider (macOS).

### Docker Desktop Resource sliders are greyed out (Windows)
Docker Desktop is using WSL2 backend — the sliders control WSL2 but may conflict with a manually created `.wslconfig`. Remove one or the other; `.wslconfig` takes precedence.

### After changing `.wslconfig`, settings didn't take effect
You must run `wsl --shutdown` AND restart Docker Desktop. Restarting Docker Desktop alone is not sufficient — it reuses the existing WSL2 VM if it's still running.
