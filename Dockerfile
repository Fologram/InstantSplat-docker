FROM nerfstudio/nerfstudio
WORKDIR /workspace/
USER root

# Install git and other required packages
RUN apt-get update && apt-get install -y git ffmpeg libsm6 libxext6 lsof

# Install cloudflare
RUN wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && \
    dpkg -i cloudflared-linux-amd64.deb && \
    rm cloudflared-linux-amd64.deb

# Install rembg
RUN pip install "rembg[gpu,cli]"

# Install pixi
RUN curl -fsSL https://pixi.sh/install.sh | bash

# Add pixi to PATH
ENV PATH="/root/.pixi/bin:${PATH}"

# Clone the repository and run the application
COPY . /workspace/InstantSplat
WORKDIR /workspace/InstantSplat

# Install dependencies using pixi
RUN pixi install 

# Make start.sh executable
RUN chmod +x start.sh

# Expose ports
EXPOSE 5000 7860

# Set the entrypoint to start.sh in the InstantSplat folder
ENTRYPOINT ["./start.sh"]
