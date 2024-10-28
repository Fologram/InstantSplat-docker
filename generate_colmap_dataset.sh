# Check if required arguments are provided
if [ $# -ne 2 ]; then
    echo "Usage: $0 <input_video> <output_directory>"
    exit 1
fi

INPUT_VIDEO="$1"
OUTPUT_DIR="$2"

# Create output directory structure
mkdir -p "$OUTPUT_DIR/images"

# Extract frames from video
ffmpeg -i "$INPUT_VIDEO" -filter:v fps=10 -qscale:v 1 "$OUTPUT_DIR/images/frame_%06d.jpg"

# Run colmap
colmap automatic_reconstructor --workspace_path "$OUTPUT_DIR" --image_path "$OUTPUT_DIR/images" --camera_model "SIMPLE_PINHOLE" --dense 0 --data_type "video" --quality "medium"

echo "COLMAP dataset generation complete. Output is in $OUTPUT_DIR"
