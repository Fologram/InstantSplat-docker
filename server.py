import os
import time
import logging
import uuid
from flask import Flask, request, jsonify
import subprocess
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Get environment variables with fallback values
PUBLIC_IPADDR = os.getenv('PUBLIC_IPADDR', 'localhost')
VAST_TCP_PORT_8080 = os.getenv('VAST_TCP_PORT_8080', '8080')

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

tasks = {}  # Dictionary to store task status and creation time
executor = ThreadPoolExecutor(max_workers=1)  # Thread pool for tasks

@app.route('/test', methods=['GET'])
def test():
    app.logger.info("Test route accessed")
    return jsonify({"status": "ok"}), 200
    
@app.route('/get_task/<task_id>', methods=['GET'])
def get_task(task_id):
    if task_id in tasks:
        task = tasks[task_id]
        elapsed_time = time.time() - task['created_at']  # Calculate elapsed time
        response = {
            'status': task['status'],
            'result': task['result'],
            'elapsed_time': round(elapsed_time, 2)  # Round to 2 decimal places
        }
        return jsonify(response)
    else:
        return jsonify({'error': 'Task not found'}), 404


@app.route('/process_video', methods=['POST'])
def process_video():
    try:
        video_url = request.json['video_url']
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            'status': 'processing',
            'result': None,
            'created_at': time.time()  # Add timestamp when creating the task
        }

        def process_video_task(task_id, video_url):
            try:
                video_name = Path(urlparse(video_url).path).stem
                timestamp = int(time.time())
                input_folder = f'data/{video_name}_{timestamp}'
                output_folder = f'output/{video_name}_{timestamp}'
                os.makedirs(input_folder, exist_ok=True)
                os.makedirs(output_folder, exist_ok=True)

                video_path = os.path.join(input_folder, 'input_video.mp4')
                logger.info(f"Downloading video from {video_url} to {video_path}")
                download_video_wget(video_url, video_path)
                
                 # Extract frames
                logger.info("Extracting frames")
                n_frames = extract_frames(video_path, input_folder, f'{input_folder}/images')
                logger.info(f"Extracted {n_frames} frames")
        
                # Run camera inference
                logger.info("Running camera inference")
                run_camera_inference(input_folder, n_frames)
        
                # Run training
                logger.info("Running training")
                run_training(input_folder, output_folder, n_frames)
        
                # Get URL for the generated PLY file
                ply_url = get_ply_url(video_name, timestamp)
                tasks[task_id]['status'] = 'complete'
                tasks[task_id]['result'] = ply_url
            except Exception as e:
                logger.error(f"Error in task {task_id}: {str(e)}", exc_info=True)
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['result'] = str(e)

        executor.submit(process_video_task, task_id, video_url)
        return jsonify({'task_id': task_id})

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def download_video_wget(video_url, download_path):
    try:
        cmd = ['wget', '-O', download_path, video_url]
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.debug(f"wget output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error downloading video with wget: {e.stderr}")
        raise
        
def extract_frames(video_path, image_folder, output_folder):
    try:
        os.makedirs(output_folder, exist_ok=True)
        # Extract 2 frames per second
        cmd = f'ffmpeg -i {video_path} -vf fps=1 {output_folder}/frame_%04d.jpg'
        logger.debug(f"Running command: {cmd}")
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"ffmpeg output: {result.stdout}")

        # Remove background (change above to image_folder dir to use this)
        #rembgCmd = f'rembg p {image_folder} {output_folder}'
        #logger.debug(f"Running command: {rembgCmd}")
        #result = subprocess.run(rembgCmd, shell=True, check=True, capture_output=True, text=True)
        
        # Count the number of extracted frames
        frames = list(Path(output_folder).glob('frame_*.jpg'))
        return len(frames)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in extract_frames: {e.output}")
        raise

def run_camera_inference(img_path, n_views):
    try:
        cmd = f'pixi run python tools/coarse_init_infer.py --img_base_path {img_path} --n_views {n_views} --focal_avg'
        logger.debug(f"Running command: {cmd}")
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"Camera inference output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in run_camera_inference: {e.output}")
        raise

def run_training(scene_path, output_path, n_views):
    try:
        cmd = f'pixi run python tools/train_joint.py -s {scene_path} -m {output_path} --n_views {n_views} --scene {Path(scene_path).name} --iter 200 --optim_pose'
        logger.debug(f"Running command: {cmd}")
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"Training output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in run_training: {e.output}")
        raise

def get_ply_url(video_name, timestamp):
    ply_path = f'InstantSplat/output/{video_name}_{timestamp}/point_cloud/iteration_200/point_cloud.ply'
    base_url = f'https://{PUBLIC_IPADDR}:{VAST_TCP_PORT_8080}'
    return f'{base_url}/files/workspace/{ply_path}'

def run_flask_server():
    app.run(debug=False, host='0.0.0.0', port=5000) #Specify host for cloudflared

if __name__ == '__main__':
    run_flask_server()
