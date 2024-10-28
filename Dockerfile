FROM nerfstudio/nerfstudio
# Create the /workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace/
USER root


### Instant Splat and Utils ###

# Install git and other required packages
RUN apt-get update && apt-get install -y git ffmpeg libsm6 libxext6 lsof

# Install cloudflare
RUN wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && \
    dpkg -i cloudflared-linux-amd64.deb && \
    rm cloudflared-linux-amd64.deb

# Install rembg
RUN pip install "rembg[gpu,cli]"

# Install flask
RUN pip install flask

# Install pixi
RUN curl -fsSL https://pixi.sh/install.sh | bash

# Add pixi to PATH
ENV PATH="/root/.pixi/bin:${PATH}"

# Clone the repository and run the application
COPY . /workspace/InstantSplat
WORKDIR /workspace/InstantSplat

# Install dependencies using pixi
RUN pixi install 

# Download model checkpoints
RUN pixi run post-install

### spann3r ###

# Install conda
RUN mkdir -p ~/miniconda3 && \
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh && \
    bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3 && \
    rm ~/miniconda3/miniconda.sh && \
    source ~/miniconda3/bin/activate && \
    conda init --all

# Install spann3r
RUN git clone https://github.com/HengyiWang/spann3r.git && \
    cd spann3r && \
    conda create -y -n spann3r python=3.9 cmake=3.14.0 && \
    conda activate spann3r && \
    conda install -y pytorch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0 pytorch-cuda=11.8 -c pytorch -c nvidia && \
    pip install -r requirements.txt && \
    pip install Open3d

# Compile curope
RUN cd spann3r/croco/models/curope/ && \
    conda activate spann3r && \
    python setup.py build_ext --inplace
    
# Download dust3r checkpoint
RUN cd spann3r && \
    mkdir checkpoints && \
    cd checkpoints && \
    wget https://download.europe.naverlabs.com/ComputerVision/DUSt3R/DUSt3R_ViTLarge_BaseDecoder_512_dpt.pth

### end spann3r ###

# Make start.sh executable
RUN chmod +x start.sh

# Expose ports
EXPOSE 5000 7860
