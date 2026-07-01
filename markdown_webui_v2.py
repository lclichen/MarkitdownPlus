"""
markitdown_webui_v2.py
======================
MarkItDown WebUI with Image Extraction & Origin Mode support.

This is the Gradio-based WebUI frontend that uses HybridConverter
from converter_core.py for document conversion.
"""

import gradio as gr
from pathlib import Path

# Import converter infrastructure from shared module
from converter_core import (
    HybridConverter,
    SUPPORTED_SUFFIXES,
)
from image_hook import package_output
from config_loader import get_webui_output_dir, get_webui_port


# ============================================================
# Gradio UI
# ============================================================

# Initialize converter (uses config from config.json)
md_converter = HybridConverter()


def convert_file(file_path, image_convert_mode_choice, progress=gr.Progress()):
    """
    Core conversion logic with progress bar.

    Returns:
        (status, md_rendering, md_text, output_file)
    """
    if file_path is None:
        return "⚠️ Please upload a file first.", "", "", None

    file_name = Path(file_path).name
    file_stem = Path(file_path).stem

    progress(0.1, desc="Preparing request...")

    try:
        progress(0.3, desc="Converting to Markdown...")

        # Convert using HybridConverter
        md_text, registry = md_converter.convert(
            file_path,
            image_convert_mode=image_convert_mode_choice,
        )

        progress(0.7, desc=f"Packaging output ({registry.count} images)...")

        # Package output
        output_dir = get_webui_output_dir()
        import os
        os.makedirs(output_dir, exist_ok=True)

        final_md, output_path = package_output(
            markdown=md_text,
            registry=registry,
            output_stem=file_stem,
            output_dir=output_dir,
        )

        progress(1.0, desc="Completed!")

        # Status info
        img_count = registry.count
        if img_count > 0:
            output_type = "ZIP" if output_path and output_path.endswith('.zip') else "MD"
            status = (
                f"✅ Converted {file_name}! "
                f"({img_count} images extracted, packaged as {output_type})"
            )
            for entry in registry.all_images():
                print(f"  📷 {entry.filename}  "
                      f"({entry.byte_size}B, {entry.processing_mode}, {entry.origin})")
        else:
            status = f"✅ Converted {file_name}! (no images)"

        return status, final_md, final_md, output_path

    except Exception as e:
        import traceback
        traceback.print_exc()
        progress(1.0, desc="Failed!")
        return f"❌ Error converting file: {str(e)}", "", "", None


def clear_all():
    """Clear all component states."""
    return (
        "Ready to convert.",
        "*Converted markdown will appear here...*",
        "*Converted markdown text will appear here...*",
        None,
        None,
    )


# Custom CSS for three-column layout
css = """
.main-header { text-align: center; margin-bottom: 20px; }
.main-header h1 { color: #2c3e50; }
.control-col { background-color: #f9f9f9; padding: 15px; border-radius: 8px; }
.preview-col { background-color: #ffffff; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; min-height: 600px; }
.result-col { background-color: #ffffff; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; min-height: 600px; }
"""

with gr.Blocks(css=css, title="MarkItDown WebUI") as demo:
    # Header
    gr.HTML("""
        <div class="main-header">
            <h1>🚀 MarkItDown WebUI</h1>
            <p>Convert various document formats to Markdown with image extraction support.</p>
        </div>
    """)

    with gr.Row():
        # Left: Control Panel
        with gr.Column(scale=1, elem_classes=["control-col"]):
            gr.Markdown("### 📁 Input")
            input_file = gr.File(label="Upload File", file_types=SUPPORTED_SUFFIXES)

            gr.Markdown("### ⚙️ Recognition Options")
            with gr.Row():
                image_convert_mode_choice = gr.Dropdown(
                    ["OCR", "Caption", "Origin"],
                    label="Image Convert Mode",
                    value="OCR",
                    info=(
                        "OCR: extract text via VLM | "
                        "Caption: generate caption via VLM | "
                        "Origin: keep as image file (no VLM)"
                    ),
                )

            gr.Markdown("### ⚙️ Actions")
            with gr.Row():
                convert_btn = gr.Button("Convert", variant="primary", scale=2)
                clear_btn = gr.ClearButton(value="Clear", scale=1, components=[input_file])

            gr.Markdown("### 📊 Status")
            status_box = gr.Textbox(
                label="Conversion Status",
                interactive=False,
                value="Ready to convert.",
            )

            gr.Markdown("### 💾 Output")
            output_file = gr.File(label="Download (MD or ZIP)", interactive=False)

        # Middle: Document Preview
        with gr.Column(scale=2, elem_classes=["preview-col"]):
    
