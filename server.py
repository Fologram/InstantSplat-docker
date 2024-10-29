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

@app.route('/get_tasks', methods=['GET'])
def get_tasks():
    task_ids = list(tasks.keys())
    return jsonify(task_ids)


@app.route('/generate', methods=['POST'])
def generate():
    try:
        video_url = request.json['video_url']
        model = request.json['model']  # New model parameter
        if model not in ['instantsplat', 'spann3r', '2dgs']:
            return jsonify({'error': 'Invalid model specified'}), 400
        
        task_id = str(uuid.uuid4())
        logger.debug(f"Creating task: {task_id}")
        tasks[task_id] = {
            'status': 'processing',
            'result': None,
            'created_at': time.time()  # Add timestamp when creating the task
        }

        def process_video_task(task_id, video_url, model, kf_every, fps, conf_thresh, iter):
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

                if model == 'instantsplat':
                    logger.info("Model: InstantSplat")
                    n_frames = extract_frames(video_path, input_folder, f'{input_folder}/images', fps)
                    run_camera_inference(input_folder, n_frames)
                    run_training(input_folder, output_folder, n_frames, iter)
                    ply_url = get_ply_url(video_name, timestamp)
                
                elif model == 'spann3r':
                    logger.info("Model: Spann3r")
                    n_frames = extract_frames(video_path, input_folder, f'{input_folder}/images', fps)
                    run_spann3r_demo(input_folder, output_folder, n_frames, kf_every, conf_thresh)
                    ply_url = get_spann3r_ply_url(output_folder)  # Return URL for Spann3r's output
                
                elif model == '2dgs':
                    logger.info("Model: 2DGS")
                    n_frames = extract_frames(video_path, input_folder, f'{input_folder}/images', fps)
                    run_colmap_and_training(output_folder, input_folder, iter)  # Run colmap and training for 2DGS
                    ply_url = get_2dgs_ply_url(output_folder)  # Return URL for 2DGS's output

                tasks[task_id]['status'] = 'complete'
                tasks[task_id]['result'] = ply_url
            except Exception as e:
                logger.error(f"Error in task {task_id}: {str(e)}", exc_info=True)
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['result'] = str(e)

        executor.submit(process_video_task, task_id, video_url, model, kf_every=5, fps=1, conf_thresh=1e-3, iter=200)
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
        
def extract_frames(video_path, image_folder, output_folder, fps=1):
    try:
        os.makedirs(output_folder, exist_ok=True)
        cmd = f'ffmpeg -i {video_path} -vf fps={fps} {output_folder}/frame_%04d.jpg'
        logger.debug(f"Running command: {cmd}")
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"ffmpeg output: {result.stdout}")

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

def run_training(scene_path, output_path, n_views, iter):
    try:
        cmd = f'pixi run python tools/train_joint.py -s {scene_path} -m {output_path} --n_views {n_views} --scene {Path(scene_path).name} --iter {iter} --optim_pose'
        logger.debug(f"Running command: {cmd}")
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"Training output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in run_training: {e.output}")
        raise

def run_spann3r_demo(input_folder, output_folder, n_views, kf_every, conf_thresh):
    try:
        # Save the current directory
        current_dir = os.getcwd()

        # Change to spann3r directory
        spann3r_dir = os.path.join(current_dir, 'spann3r')
        os.chdir(spann3r_dir)
        
        # Activate spann3r environment and run demo script
        cmd = f'conda run -n spann3r python demo.py --demo_path ../{input_folder}/images --kf_every {kf_every} --save_path ../{output_folder} --conf_thresh {conf_thresh}'
        logger.debug(f"Running Spann3r command: {cmd}")
        
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"Spann3r output: {result.stdout}")

    except subprocess.CalledProcessError as e:
        logger.error(f"Error in Spann3r demo: {e.output}")
        raise

    finally:
        # Change back to the original directory
        os.chdir(current_dir)
        
def get_spann3r_ply_url(output_folder):
    # Define the logic to get the PLY file URL for Spann3r
    ply_path = f'InstantSplat/{output_folder}/images/images_conf0.001.ply'
    base_url = f'https://{PUBLIC_IPADDR}:{VAST_TCP_PORT_8080}'
    return f'{base_url}/files/workspace/{ply_path}'
    
def get_ply_url(video_name, timestamp):
    ply_path = f'InstantSplat/output/{video_name}_{timestamp}/point_cloud/iteration_200/point_cloud.ply'
    base_url = f'https://{PUBLIC_IPADDR}:{VAST_TCP_PORT_8080}'
    return f'{base_url}/files/workspace/{ply_path}'

def run_colmap_and_training(output_folder, image_folder, iter):
    try:
        # Run COLMAP to generate the dataset
        colmap_cmd = f'colmap automatic_reconstructor --workspace_path "{output_folder}" --image_path "{image_folder}" --camera_model "SIMPLE_PINHOLE" --dense 0 --data_type "video" --quality "medium"'
        logger.debug(f"Running COLMAP command: {colmap_cmd}")
        result = subprocess.run(colmap_cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"COLMAP output: {result.stdout}")

        # Run training script
        train_cmd = f'python 2d-gaussian-splatting/train.py -s ../{output_folder} --iterations {iter}'
        logger.debug(f"Running training command: {train_cmd}")
        result = subprocess.run(train_cmd, shell=True, check=True, capture_output=True, text=True)
        logger.debug(f"Training output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in COLMAP and training: {e.output}")
        raise

def get_2dgs_ply_url(output_folder):
    # Define the logic to get the PLY file URL for 2DGS
    ply_path = f'InstantSplat/{output_folder}/colmap_output.ply'
    base_url = f'https://{PUBLIC_IPADDR}:{VAST_TCP_PORT_8080}'
    return f'{base_url}/files/workspace/{ply_path}'

def run_flask_server():
    app.run(debug=False, host='0.0.0.0', port=5000) #Specify host for cloudflared

if __name__ == '__main__':
    run_flask_server()
