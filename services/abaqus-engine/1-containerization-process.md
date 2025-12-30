# DevOps Runbook: Abaqus-in-a-Bottle (Abaqus LE 2024 on Linux via Wine)

This document is an Engineering Manual and DevOps Runbook for reproducing the Abaqus-in-a-Bottle Gold Image.
It captures the exact technical maneuvers used to overcome 4GB RAM and "No Space Left" constraints when running Windows-native Abaqus LE 2024 inside a Linux container.

The approach is based on the mwierszycki protocol, adapted for cloud-native, low-resource workers.

## Architecture Overview

- **Host OS:** Linux VM
- **Container Base:** `kasmweb/ubuntu-jammy-desktop`
- **GUI Access:** Browser-based VNC over HTTP
- **Windows Compatibility:** Wine (Windows 10 mode)
- **Target Runtime:** 2 vCPU / 4GB RAM Linux workers
- **Final Image Size:** ~20GB

## 1. Hardware Selection (Host VM)

⚠️ **Do NOT use a 30GB disk during image creation.**  
Docker requires substantial scratch space when committing layers.

### Minimum Specs

- **CPU:** 2 vCPU
- **RAM:** 4GB
- **Disk:** 50GB+ SSD (creation phase)
- **Network:** TCP 6901 open (VNC-over-HTTP)

## 2. Host Preparation

Install Docker and grant non-root execution permissions.

```bash
sudo apt update && sudo apt install docker.io -y
sudo usermod -aG docker $USER && newgrp docker
```

## 3. Launching the Base Environment

We use a Kasm Ubuntu desktop image because it includes Xvfb, which is required for GUI applications like Abaqus.

```bash
docker run -d --name abq_builder \
  -p 6901:6901 \
  -e VNC_PW=password123 \
  --shm-size=1g \
  kasmweb/ubuntu-jammy-desktop:1.14.0
```

### Why `--shm-size=1g`?

The Docker default (64MB) is insufficient for Wine + Abaqus memory mapping and will cause:

- Random crashes
- "Out of Memory" errors
- GUI launch failures

## 4. Inside the Container: Installation Phase

Access the desktop at:

```
https://<VM_IP>:6901
```

Open the terminal inside the browser session.

### A. Environment Prerequisites

Update the system and install required dependencies.

```bash
sudo apt update
sudo apt install -y openjdk-17-jre wine64 winbind
```

- **Java:** Required for Abaqus installer
- **Wine:** Windows compatibility layer
- **Winbind:** Prevents Wine authentication issues

### B. Following the mwierszycki Protocol

This approach bypasses the Windows-only installer checks.

1. **Download & Extract**

   Upload the Abaqus LE 2024 ZIP into the container and extract it.

2. **Configure Wine**

   Initialize the Wine prefix and set Windows version to Windows 10.

   ```bash
   winecfg
   ```

   In the GUI, select Windows 10, then close.

3. **Run the Installer**

   ```bash
   wine explorer /desktop=Abaqus,1280x720 /home/kasm_user/Abaqus_Installer/setup.exe
   ```

   This launches the Abaqus GUI installer inside the virtual desktop.

### C. Resource Cleanup (🚨 CRITICAL)

Before committing the image, ALL installers and caches must be removed.

Failure to do this will inflate the image beyond 40GB, causing docker commit to fail.

```bash
rm -rf ~/Abaqus_Installer
rm -f ~/abaqus_setup.zip
sudo apt-get clean
rm -rf ~/.cache/wine
```

## 5. Image Creation (The "Gold" Commit)

From the host VM SSH terminal:

```bash
# Verify writable layer size (should be ~12–13GB)
docker ps -s

# Commit the container
docker commit abq_builder abaqus_2024_le:v1
```

⚠️ **Never use docker export/import**  
It strips Wine metadata, symlinks, and breaks the C: drive.

## 6. Edge Cases & Troubleshooting

| Issue             | Cause                               | Fix                                            |
| ----------------- | ----------------------------------- | ---------------------------------------------- |
| No Space Left     | Docker commit duplicates filesystem | Ensure host disk has 2× container size         |
| GUI won't open    | Shared memory exhausted             | Use `--shm-size=1g`                            |
| Wine C: missing   | Used export/import                  | Always use docker commit                       |
| Permission denied | UID mismatch                        | `chown -R kasm_user:kasm_user /home/kasm_user` |

## 7. Cloud Deployment (Azure Container Registry)

Push the Gold Image to a private ACR for orchestration.

```bash
# Login
az acr login --name abaqusregistry

# Tag
docker tag abaqus_2024_le:v1 abaqusregistry.azurecr.io/abaqus_2024_le:v1

# Push (20–30 minutes for ~20GB)
docker push abaqusregistry.azurecr.io/abaqus_2024_le:v1
```

## 8. Final Worker Execution Command

Run Abaqus on a 4GB RAM node while still allowing browser-based inspection.

```bash
docker run -d \
  --name abq_worker \
  -p 6901:6901 \
  -p 5000:5000 \
  --shm-size=1g \
  --memory="3.5g" \
  -e VNC_PW=password123 \
  -v /mnt/abaqus_data:/home/kasm_user/work \
  abaqusregistry.azurecr.io/abaqus_2024_le:v1
```

## References

- **mwierszycki** – Abaqus LE on Linux via Wine (2024)  
  https://github.com/mwierszycki/abaqus_le_linux_wine/tree/main/2024


