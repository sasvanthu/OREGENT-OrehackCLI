# OREHACK AI Evaluation Engine - Docker Setup

This guide explains how to package, distribute, and run the OREHACK AI Evaluation Engine using Docker. 
The system features an **Auto-Updater** that automatically downloads the latest code from GitHub every time it starts, meaning your admins never have to manually update their files!

---

## Part 1: For the Organizer (Setting up the Distribution)

You do not need to send your admins the entire source code. You only need to send them a small ZIP file containing the Docker configuration.

### 1. Create the Admin ZIP File
Create a `.zip` file containing **only** these 4 files from your root directory:
1. `docker-compose.yml`
2. `Dockerfile`
3. `entrypoint.sh`
4. `.env` (Make sure your Supabase keys are inside this file!)

Distribute this ZIP file to your admins.

### 2. Reset the Database for a Fresh Evaluation
If you have old evaluation scores from past testing or previous hackathons and want to clear them out so the AI can evaluate them fresh, run this SQL query in your **Supabase SQL Editor**:

```sql
UPDATE "submissions"
SET 
    "Progress" = 'queued',
    "Total_Scores" = NULL,
    "Tech_Scores" = NULL,
    "Innov_Scores" = NULL,
    "Completeness_Scores" = NULL,
    "Reasoning" = NULL,
    "claimed_at" = NULL,
    "retry_count" = 0,
    "last_error" = NULL;
```
*This completely clears out previous scores and errors without deleting any rows or team data.*

---

## Part 2: For the Admins (Running the Engine)

If you have been given the OREHACK Docker ZIP file, follow these instructions to start your evaluation engine.

### Prerequisites
1. Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop).
2. Ensure Docker Desktop is open and running in the background.

### Quick Start
1. **Extract the ZIP file** you were given into an empty folder on your computer.
2. Open a terminal (or Command Prompt / PowerShell) in that folder.
3. Run the following command:

```bash
docker compose up --build
```

### What happens automatically?
1. **Auto-Updater:** The script securely connects to GitHub and downloads the latest OREHACK source code into the container.
2. **Dependencies:** It installs all required Python packages.
3. **Hardware Detection:** It checks your RAM to ensure you can run the AI.
4. **Model Download:** If this is your first time, it downloads the 4GB `deepseek-coder:6.7b` AI brain automatically (this saves permanently, you only wait for this once).
5. **Evaluation:** It starts the worker, connects to the database, and automatically starts reading and grading hackathon submissions!

### To Stop the Engine
Press `Ctrl + C` in the terminal where it is running. Your downloaded AI model will be safely saved for next time.

---

## Troubleshooting

### "Insufficient Memory" Error
If the script detects you don't have enough RAM for `deepseek-coder:6.7b`, it will safely exit.
To fix this, edit the `.env` file and append this line to the bottom:
```env
OLLAMA_MODEL=deepseek-coder:1.3b
```
Then restart using `docker compose up --build`.

### Enabling NVIDIA GPU Support (Optional)
If your computer has an NVIDIA GPU, you can speed up the AI:
1. Open `docker-compose.yml`.
2. Scroll to the bottom and uncomment the `deploy` block under the `ollama` service:
```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```
*(Requires the NVIDIA Container Toolkit to be installed on your host system).*
