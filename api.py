import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

# Import the upload function from your existing project
# Adjust this import path if your project structure is different
from tiktok_uploader.tiktok import upload_video as tiktok_upload_video
from tiktok_uploader.Config import Config

app = FastAPI()

# Initialize Config (if needed by tiktok_upload_video, otherwise can be removed)
# Ensure your Config class can be initialized without issues in an API context
# For example, if it reads from a config.txt, make sure that file is accessible
Config.get() 

@app.post("/upload")
async def upload_tiktok_video(
    video_file: UploadFile = File(...),
    session_file: UploadFile = File(...),
    caption: str = Form(...),
    schedule_time: int = Form(0),
    allow_comment: int = Form(1),
    allow_duet: int = Form(0),
    allow_stitch: int = Form(0),
    visibility_type: int = Form(0),
    brand_organic_type: int = Form(0),
    branded_content_type: int = Form(0),
    ai_label: int = Form(0),
    proxy: str = Form(None),
    datacenter: str = Form(None)
):
    temp_dir = None
    video_path = None
    session_path = None

    try:
        # Create a temporary directory for this upload
        temp_dir = tempfile.mkdtemp()
        
        # Save the uploaded video file
        video_path = Path(temp_dir) / video_file.filename
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        # Save the uploaded session file
        session_path = Path(temp_dir) / session_file.filename
        with open(session_path, "wb") as buffer:
            shutil.copyfileobj(session_file.file, buffer)

        # Call the existing upload function
        # The upload_video function needs to be adapted to accept the session_path directly
        # instead of a session_user string. This will be the next step.
        success = tiktok_upload_video(
            session_file_path=str(session_path), # Pass the path to the session file
            video=str(video_path),
            title=caption,
            schedule_time=schedule_time,
            allow_comment=allow_comment,
            allow_duet=allow_duet,
            allow_stitch=allow_stitch,
            visibility_type=visibility_type,
            brand_organic_type=brand_organic_type,
            branded_content_type=branded_content_type,
            ai_label=ai_label,
            proxy=proxy,
            datacenter=datacenter
        )

        if success:
            return JSONResponse(status_code=200, content={"message": "Video uploaded successfully!"})
        else:
            raise HTTPException(status_code=500, detail="Failed to upload video to TikTok.")

    except Exception as e:
        print(f"Error during upload: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    finally:
        # Clean up the temporary directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
