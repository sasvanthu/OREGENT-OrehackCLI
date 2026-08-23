# Dockerizing OREHACK

This guide explains how to run the OREHACK Evaluation Engine using Docker. The setup is fully automated, handling dependency installation, hardware detection, and Ollama model management.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running.
- `.env` file present in the root directory with Supabase keys configured.

## Quick Start

To start the OREHACK worker along with the Ollama service, simply run:

```bash
docker compose up --build
```

### What happens automatically?
1. **Hardware Detection:** The container will check your system's memory, CPU, disk space, and check for an NVIDIA GPU.
2. **Model Validation:** It ensures your hardware can handle the requested Ollama model (default requires at least 4GB RAM).
3. **Model Download:** If the model isn't installed locally, it will automatically pull the model from Ollama (this will take a few minutes the first time).
4. **App Startup:** Once the model is ready, the `worker.py` polling daemon will start.

## Using a Smaller Model (If you have < 5GB RAM)

If the startup script detects you don't have enough memory for `deepseek-coder:6.7b`, it will safely exit.
To fix this, edit your `.env` file and append:

```env
OLLAMA_MODEL=deepseek-coder:1.3b
```
Then restart using `docker compose up --build`.

## Enabling NVIDIA GPU Support

If your system has an NVIDIA GPU, you can significantly speed up inference.
1. Open `docker-compose.yml`.
2. Scroll to the bottom of the `ollama` service configuration.
3. Uncomment the `deploy` block:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```
*Note: This requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) to be installed.*
