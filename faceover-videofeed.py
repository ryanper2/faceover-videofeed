'''
Python Faceover Camera Video Feed.

Ryan Pereira
With the help of gemini flash 2.5

Tested on Python 3.11.7 & Mac M1 Pro - Sequoia
'''


import sys
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QPushButton,
    QSlider, QGroupBox, QGridLayout, QHBoxLayout, QColorDialog
)
from PySide6.QtCore import (
    QTimer, Qt, QRect 
)
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QBitmap, QColor 
) 

# --- Configuration ---
DEFAULT_WINDOW_SIZE = 250  
DEFAULT_BORDER_RADIUS = 12 
CAMERA_INDEX = 0           
DEFAULT_BORDER_COLOR = "#343434" # Initial default grey color

class FaceFeedApp(QWidget):
    """
    A frameless, always-on-top window displaying a live camera feed.
    The video feed now automatically zooms and crops (Aspect Fill) to perfectly 
    fill the inner window content area, removing any black bars.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Always-On-Top Face Feed")
        
        # Internal state variables
        self.border_radius = DEFAULT_BORDER_RADIUS
        self.border_width = 5 
        self.border_color = DEFAULT_BORDER_COLOR # NEW: State for border color
        
        # Stores the desired total physical size of the window (the unified size control)
        self.window_w = DEFAULT_WINDOW_SIZE
        self.window_h = DEFAULT_WINDOW_SIZE
        
        self.zoom_level = 1.0 
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.is_visible = True
        
        # 1. Initialize Window Properties
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0);") 

        # 2. Setup Camera
        self.capture = cv2.VideoCapture(CAMERA_INDEX)
        if not self.capture.isOpened():
            print(f"Error: Could not open camera with index {CAMERA_INDEX}.")
            QApplication.quit()
            return

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1920) #640
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080) #480
        
        # 3. Setup UI
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter) 

        main_layout = QGridLayout()
        main_layout.addWidget(self.image_label, 0, 0, 1, 1, Qt.AlignmentFlag.AlignCenter)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)
        
        # 4. Apply initial size, mask, and style
        self._apply_size_and_mask() 

        # 5. Setup Timer for Continuous Frame Updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)  # ~33 FPS

        # Variables for dragging the window
        self._drag_start_position = None

    def _get_total_window_size(self):
        """Returns the total fixed size for the QWidget (main window)."""
        return self.window_w, self.window_h

    def _get_label_stylesheet(self):
        """
        Generates the stylesheet for the QLabel, including the dynamic border color.
        """
        return f"""
            QLabel {{
                border-radius: {self.border_radius}px; 
                overflow: hidden;
                margin: 0px; 
                padding: 0px;
                outline: none;
                
                /* Border color now dynamically set */
                border: {self.border_width}px solid {self.border_color}; 
                background-color: black; 
            }}
        """
    
    def _update_window_mask(self):
        """
        Creates a rounded rectangular mask and applies it to the main widget.
        """
        size_w, size_h = self._get_total_window_size() 
        radius = self.border_radius
        
        mask = QBitmap(size_w, size_h)
        painter = QPainter(mask)
        
        painter.fillRect(mask.rect(), Qt.GlobalColor.white)
        painter.setBrush(Qt.GlobalColor.black)
        painter.setPen(Qt.PenStyle.NoPen)
        
        effective_radius_w = min(radius, size_w // 2)
        effective_radius_h = min(radius, size_h // 2)
        effective_radius = min(effective_radius_w, effective_radius_h)

        painter.drawRoundedRect(
            QRect(0, 0, size_w, size_h), 
            effective_radius, 
            effective_radius
        )
        painter.end()
        self.setMask(mask)

    def _apply_size_and_mask(self):
        """Centralized method to apply all size, style, and mask changes."""
        
        # 1. Set the size of the MAIN QWidget (the Frame/Mask)
        total_w, total_h = self._get_total_window_size()
        self.setFixedSize(total_w, total_h)

        # 2. Set the size of the QLabel to match the window size (it will cover the whole area)
        self.image_label.setFixedSize(total_w, total_h)
        
        # 3. Update the stylesheet (which includes the border properties and color)
        self.image_label.setStyleSheet(self._get_label_stylesheet())
        
        # 4. Update the physical mask
        self._update_window_mask()
        
        # Reposition to prevent visual drift
        current_pos = self.pos()
        self.move(current_pos.x(), current_pos.y())
        
    # --- Control Setters ---

    def set_window_width(self, width):
        self.window_w = max(10, width)
        self._apply_size_and_mask()

    def set_window_height(self, height):
        self.window_h = max(10, height)
        self._apply_size_and_mask()

    def set_border_radius(self, radius):
        self.border_radius = radius
        self._apply_size_and_mask()

    def set_border_width(self, width):
        self.border_width = width
        self._apply_size_and_mask()

    def set_border_color(self, color):
        """NEW: Setter for border color."""
        self.border_color = color
        self._apply_size_and_mask()
        
    def set_zoom_level(self, zoom):
        self.zoom_level = max(1.0, zoom)
        
    def set_pan_x(self, pan_x):
        self.pan_x = pan_x

    def set_pan_y(self, pan_y):
        self.pan_y = pan_y

    def toggle_visibility(self):
        self.is_visible = not self.is_visible
        if self.is_visible:
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            self.hide()

    def update_frame(self):
        """Reads a frame, applies manual zoom/pan, applies aspect-fill crop, and displays it."""
        ret, frame = self.capture.read()
        if not ret:
            return

        # 1. Flip the frame
        frame = cv2.flip(frame, 1)
        
        # 2. Apply Manual Digital Zoom/Crop and Pan
        if self.zoom_level > 1.0:
            h, w, _ = frame.shape
            
            crop_factor = 1.0 / self.zoom_level
            crop_w = int(w * crop_factor)
            crop_h = int(h * crop_factor)
            
            max_offset_x = (w - crop_w) // 2
            max_offset_y = (h - crop_h) // 2
            
            start_x = max_offset_x + int(self.pan_x * max_offset_x)
            start_y = max_offset_y + int(self.pan_y * max_offset_y)

            start_x = max(0, min(start_x, w - crop_w))
            start_y = max(0, min(start_y, h - crop_h))
            
            # This frame is now the result of manual zooming/panning
            frame = frame[start_y:start_y + crop_h, start_x:start_x + crop_w]

        # 3. Calculate the available content area inside the border
        content_w = self.window_w - (self.border_width * 2)
        content_h = self.window_h - (self.border_width * 2)
        
        content_w = max(1, content_w)
        content_h = max(1, content_h)

        # 4. Apply "Zoom to Fill" Crop (Aspect Fill)
        src_h, src_w, _ = frame.shape
        src_ar = src_w / src_h
        target_ar = content_w / content_h
        
        crop_start_x, crop_end_x = 0, src_w
        crop_start_y, crop_end_y = 0, src_h
        
        if target_ar > src_ar:
            # Target is wider, crop the TOP and BOTTOM (vertical crop).
            new_src_h = int(src_w / target_ar)
            
            crop_amount_y = (src_h - new_src_h) // 2
            crop_start_y = crop_amount_y
            crop_end_y = src_h - crop_amount_y
            
        elif target_ar < src_ar:
            # Target is taller, crop the LEFT and RIGHT (horizontal crop).
            new_src_w = int(src_h * target_ar)
            
            crop_amount_x = (src_w - new_src_w) // 2
            crop_start_x = crop_amount_x
            crop_end_x = src_w - crop_amount_x
        
        # Apply the final Aspect-Fill crop
        final_cropped_frame = frame[crop_start_y:crop_end_y, crop_start_x:crop_end_x]
        
        # 5. Resize to fill the entire content area exactly
        try:
            resized_frame = cv2.resize(final_cropped_frame, (content_w, content_h), interpolation=cv2.INTER_LINEAR)
        except cv2.error as e:
            print(f"Resize error: {e}")
            return
            
        canvas = resized_frame

        # 6. Convert canvas to QPixmap and display
        rgb_image = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        
        convert_to_qt_format = QImage(
            rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
        )
        
        pixmap = QPixmap.fromImage(convert_to_qt_format)
        
        self.image_label.setPixmap(pixmap)


    # --- Window Dragging Implementation ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self._drag_start_position is not None:
                self.move(event.globalPosition().toPoint() - self._drag_start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_start_position = None
        event.accept()
        
    def closeEvent(self, event):
        self.capture.release()
        event.accept()


class ControlPanel(QWidget):
    """
    A separate window to control the FaceFeedApp instance.
    """
    def __init__(self, face_feed_app: FaceFeedApp):
        super().__init__()
        self.setWindowTitle("Feed Controls")
        self.face_feed_app = face_feed_app
        self.setFixedWidth(280)
        
        # Apply global styles
        self.setStyleSheet("""
            QWidget {
                background-color: #f3f4f6;
                font-family: Arial, sans-serif;
            }
            QGroupBox {
                border: 2px solid #D1D5DB;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 20px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 10px;
                color: #1F2937;
                font-weight: bold;
            }
            /* Default QPushButton style for the Toggle button */
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QSlider::groove:horizontal {
                border: 1px solid #D1D5DB;
                height: 8px;
                background: #E5E7EB;
                margin: 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4B5563;
                border: 1px solid #1F2937;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            .pan_label {
                font-size: 10px;
                color: #6B7280;
                padding-top: 4px;
            }
        """)

        self.setup_ui()

    def setup_ui(self):
        """Sets up the layout and widgets for the control panel."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # 1. Toggle Button
        self.toggle_button = QPushButton("🔴 Hide Feed")
        self.toggle_button.clicked.connect(self.toggle_feed)
        main_layout.addWidget(self.toggle_button)
        
        # 2. WINDOW SIZE Group Box
        window_size_group = QGroupBox("Window Size (Pixels)")
        window_size_layout = QGridLayout()
        window_size_group.setLayout(window_size_layout)
        
        initial_window_size = self.face_feed_app.window_w

        # Window Width Slider
        self.window_width_label = QLabel(f"Current Width: {initial_window_size}px")
        self.window_width_label.setStyleSheet("QLabel { color: #868686; background-color: white; }}")
        window_size_layout.addWidget(self.window_width_label, 0, 0, 1, 2)
        
        self.window_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.window_width_slider.setStyleSheet("QSlider { background-color: white; }}")
        self.window_width_slider.setRange(100, 500) 
        self.window_width_slider.setValue(initial_window_size)
        self.window_width_slider.setSingleStep(10)
        self.window_width_slider.valueChanged.connect(self.update_window_width)
        window_size_layout.addWidget(self.window_width_slider, 1, 0, 1, 2)
        
        # Window Height Slider
        self.window_height_label = QLabel(f"Current Height: {initial_window_size}px")
        self.window_height_label.setStyleSheet("QLabel { color: #868686; background-color: white; }}")
        window_size_layout.addWidget(self.window_height_label, 2, 0, 1, 2)
        
        self.window_height_slider = QSlider(Qt.Orientation.Horizontal)
        self.window_height_slider.setStyleSheet("QSlider { background-color: white; }}")
        self.window_height_slider.setRange(100, 500) 
        self.window_height_slider.setValue(initial_window_size)
        self.window_height_slider.setSingleStep(10)
        self.window_height_slider.valueChanged.connect(self.update_window_height)
        window_size_layout.addWidget(self.window_height_slider, 3, 0, 1, 2)
        
        main_layout.addWidget(window_size_group)

        # 3. Zoom/Crop Group Box 
        zoom_group = QGroupBox("Digital Zoom / Crop")
        zoom_layout = QGridLayout()
        zoom_group.setLayout(zoom_layout)

        self.zoom_label = QLabel("Current Zoom: 1.0x")
        self.zoom_label.setStyleSheet("QLabel { color: #868686; background-color: white; }}")
        zoom_layout.addWidget(self.zoom_label, 0, 0, 1, 2)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setStyleSheet("QSlider { background-color: white; }}")
        self.zoom_slider.setRange(10, 30) 
        self.zoom_slider.setValue(10) 
        self.zoom_slider.setSingleStep(1)
        self.zoom_slider.valueChanged.connect(self.update_zoom)
        zoom_layout.addWidget(self.zoom_slider, 1, 0, 1, 2)

        main_layout.addWidget(zoom_group)

        # 4. Border Group Box
        border_group = QGroupBox("Border & Rounding")
        border_layout = QGridLayout()
        border_group.setLayout(border_layout)
        
        # Radius Slider
        self.radius_label = QLabel(f"Current Radius: {DEFAULT_BORDER_RADIUS}px")
        self.radius_label.setStyleSheet("QLabel { color: #868686; background-color: white; }}")
        border_layout.addWidget(self.radius_label, 0, 0, 1, 2)

        self.radius_slider = QSlider(Qt.Orientation.Horizontal)
        self.radius_slider.setStyleSheet("QSlider { background-color: white; }}")
        self.radius_slider.setRange(0, 100)
        self.radius_slider.setValue(DEFAULT_BORDER_RADIUS)
        self.radius_slider.setSingleStep(1)
        self.radius_slider.valueChanged.connect(self.update_border_radius)
        border_layout.addWidget(self.radius_slider, 1, 0, 1, 2)
        
        # Width Slider
        self.border_width_label = QLabel(f"Current Width: {self.face_feed_app.border_width}px")
        self.border_width_label.setStyleSheet("QLabel { color: #868686; background-color: white; }}")
        border_layout.addWidget(self.border_width_label, 2, 0, 1, 2)

        self.width_slider_control = QSlider(Qt.Orientation.Horizontal)
        self.width_slider_control.setRange(0, 20)
        self.width_slider_control.setValue(self.face_feed_app.border_width)
        self.width_slider_control.setSingleStep(1)
        self.width_slider_control.valueChanged.connect(self.update_border_width)
        border_layout.addWidget(self.width_slider_control, 3, 0, 1, 2)

        # NEW: Color Picker Button
        self.color_button = QPushButton("Border Color: Click to Select")
        self.color_button.clicked.connect(self.choose_border_color)
        # Span 2 columns for a better look
        border_layout.addWidget(self.color_button, 4, 0, 1, 2)
        
        # Set initial color style
        self._update_color_button_style(self.face_feed_app.border_color)
        
        main_layout.addWidget(border_group)
        
        # 5. Pan/Movement Group Box 
        pan_group = QGroupBox("Pan / Movement (Zoom > 1.0x)")
        pan_layout = QVBoxLayout()
        pan_group.setLayout(pan_layout)
        
        # Horizontal Pan

        self.pan_x_lable = QLabel("Horizontal Pan (Left <-> Right):")
        self.pan_x_lable.setStyleSheet("QLabel { color: #868686; background-color: white; }}")
        pan_layout.addWidget(self.pan_x_lable)

        #pan_layout.addWidget(QLabel("Horizontal Pan (Left <-> Right):"))

        self.pan_x_slider = QSlider(Qt.Orientation.Horizontal)
        self.pan_x_slider.setStyleSheet("QSlider { background-color: white; }}")
        self.pan_x_slider.setRange(-10, 10)
        self.pan_x_slider.setValue(0)
        self.pan_x_slider.setSingleStep(1)

        pan_layout.addWidget(self.pan_x_slider)
        
        '''
        pan_info_x = QHBoxLayout()
        pan_info_x.addWidget(QLabel("Left", objectName="pan_label"))
        pan_info_x.addStretch(1)
        pan_info_x.addWidget(QLabel("Center", objectName="pan_label"))
        pan_info_x.addStretch(1)
        pan_info_x.addWidget(QLabel("Right", objectName="pan_label"))
        pan_layout.addLayout(pan_info_x)
        '''

        self.pan_x_slider.valueChanged.connect(self.update_pan_x)
        

        # Vertical Pan

        self.pan_y_lable = QLabel("Vertical Pan (Up <-> Down):")
        self.pan_y_lable.setStyleSheet("QLabel { color: #868686; background-color: white; }}")
        pan_layout.addWidget(self.pan_y_lable)

        #pan_layout.addWidget(QLabel("Vertical Pan (Up <-> Down):"))

        self.pan_y_slider = QSlider(Qt.Orientation.Horizontal)
        self.pan_y_slider.setStyleSheet("QSlider { background-color: white; }}")
        self.pan_y_slider.setRange(-10, 10)
        self.pan_y_slider.setValue(0)
        self.pan_y_slider.setSingleStep(1)
        pan_layout.addWidget(self.pan_y_slider)
        
        '''
        pan_info_y = QHBoxLayout()
        pan_info_y.addWidget(QLabel("Up", objectName="pan_label"))
        pan_info_y.addStretch(1)
        pan_info_y.addWidget(QLabel("Center", objectName="pan_label"))
        pan_info_y.addStretch(1)
        pan_info_y.addWidget(QLabel("Down", objectName="pan_label"))
        pan_layout.addLayout(pan_info_y)
        '''

        self.pan_y_slider.valueChanged.connect(self.update_pan_y)
        
        main_layout.addWidget(pan_group)
        
        main_layout.addStretch(1)

    # --- New Color Picker Methods ---

    def _update_color_button_style(self, hex_color):
        """Updates the color button style to reflect the current border color."""
        color = QColor(hex_color)
        r, g, b, _ = color.getRgb()
        # Simple luminance calculation to decide if text should be black or white
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        text_color = 'black' if luminance > 0.5 else 'white'
        
        self.color_button.setText(f"Border Color: {hex_color.upper()}")
        self.color_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {hex_color};
                color: {text_color};
                border: 2px solid #374151; /* Darker border for contrast */
                padding: 5px 10px;
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: #000000;
            }}
        """)


    def choose_border_color(self):
        """Opens a color dialog and sets the new border color in the feed app."""
        initial_color = QColor(self.face_feed_app.border_color)
        color = QColorDialog.getColor(initial_color, self, "Select Border Color")
        
        if color.isValid():
            hex_color = color.name()
            self.face_feed_app.set_border_color(hex_color)
            self._update_color_button_style(hex_color)

    # --- Existing Control Update Methods ---
    
    def toggle_feed(self):
        self.face_feed_app.toggle_visibility()
        if self.face_feed_app.is_visible:
            self.toggle_button.setText("🔴 Hide Feed")
            self.toggle_button.setStyleSheet("background-color: #10B981; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold;")
        else:
            self.toggle_button.setText("🟢 Show Feed")
            self.toggle_button.setStyleSheet("background-color: #EF4444; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold;")

    def update_window_width(self, value):
        self.window_width_label.setText(f"Current Width: {value}px")
        self.face_feed_app.set_window_width(value)
        
    def update_window_height(self, value):
        self.window_height_label.setText(f"Current Height: {value}px")
        self.face_feed_app.set_window_height(value)
        
    def update_border_radius(self, value):
        self.radius_label.setText(f"Current Radius: {value}px")
        self.face_feed_app.set_border_radius(value)

    def update_border_width(self, value):
        self.border_width_label.setText(f"Current Width: {value}px")
        self.face_feed_app.set_border_width(value)
        
    def update_zoom(self, value):
        zoom = value / 10.0
        self.zoom_label.setText(f"Current Zoom: {zoom:.1f}x")
        self.face_feed_app.set_zoom_level(zoom)
        
    def update_pan_x(self, value):
        pan_x = value / 10.0
        self.face_feed_app.set_pan_x(pan_x)

    def update_pan_y(self, value):
        pan_y = value / 10.0
        self.face_feed_app.set_pan_y(pan_y)

def run_app():
    """Initializes and runs the PySide application with both windows."""
    app = QApplication(sys.argv)
    
    # 1. Initialize the main face feed window
    face_feed_window = FaceFeedApp()
    
    # Check if camera initialization failed
    if not face_feed_window.capture.isOpened():
        sys.exit(-1)

    # 2. Initialize the control panel
    control_panel = ControlPanel(face_feed_window)

    # 3. Positioning the windows
    screen_rect = app.primaryScreen().geometry()
    
    total_w, total_h = face_feed_window._get_total_window_size() 
    
    # Position the face feed in the top-right corner
    x_feed = screen_rect.width() - total_w - 20 
    y_feed = 20
    face_feed_window.move(x_feed, y_feed)
    face_feed_window.show()
    
    # Explicitly raise and activate the window to enforce layering
    face_feed_window.raise_()
    face_feed_window.activateWindow()

    # Position the control panel to the left of the face feed
    x_control = x_feed - control_panel.width() - 20
    y_control = y_feed
    control_panel.move(x_control, y_control)
    control_panel.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    run_app()
