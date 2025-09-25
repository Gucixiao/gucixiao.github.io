# pet.py
import sys
import os
import random
import time
import json
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QMenu, QSlider, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer, QPoint, QUrl, QEvent
from PyQt5.QtGui import QPixmap, QTransform, QCursor, QIcon
from PyQt5.QtMultimedia import QSoundEffect

# ================== 打包路径 ==================
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
    exe_dir = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
    exe_dir = os.path.dirname(os.path.abspath(__file__))


class DesktopPet(QWidget):

    FRAME_MS = 33  # 帧间隔，约 30 FPS

    def __init__(self):
        super().__init__()

        # ---------- CONFIG ----------
        self.config_path = os.path.join(exe_dir, "config.json")

        # 默认配置，详细注释
        self.default_config = {
            "timers": {
                "leave_delay": 1000,             # 鼠标离开后多少毫秒触发 fly->idle
                "idle_sleep_delay": 3000,        # idle 状态下多少毫秒后进入 sleeping
                "volume_widget_close_delay": 1500, # 音量控件离开后多少毫秒自动关闭
                "bark_cooldown": 500,            # bark 冷却时间（ms）
                "fade_out_duration": 500         # 音效淡出时间（ms）
            },
            "volume": {
                "prev_volume": 20,               # 上次音量
                "mute_on_start": False           # 启动时是否静音
            },
            "default_state": "fly",              # 默认状态
            "scale_dict": {                      # 各动作缩放比例
                "idle": 2.5,
                "sleeping": 1.0,
                "stuck": 1.3,
                "bark": 2.4,
                "fly": 2.0,
                "dive": 1.0,
                "floating": 1.0,
                "struggle": 2.1,
                "shake": 1.0
            },
            "offset_dict": {                     # 各动作 Y 方向偏移，正数下移
                "idle": 50,
                "fly": -40,
                "bark": -40
            },
            "position": {
                "x": None,                        # 上次保存的宠物 X 坐标
                "y": None                         # 上次保存的宠物 Y 坐标
            }
        }

        # 读取 config，如果文件不存在或解析失败就创建默认
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.default_config, f, indent=4)
            self.config = self.default_config

        # ---------- TIMERS ----------
        self.leave_delay = self.config["timers"].get("leave_delay", 1000)
        self.idle_sleep_delay = self.config["timers"].get("idle_sleep_delay", 3000)
        self.bark_cooldown = self.config["timers"].get("bark_cooldown", 500)
        self.fade_out_duration = self.config["timers"].get("fade_out_duration", 500)
        self.volume_widget_close_delay = self.config["timers"].get("volume_widget_close_delay", 1500)

        # ---------- BASE & SCALE/OFFSET ----------
        self.base_width = 192
        self.base_height = 192
        self.scale_dict = self.config.get("scale_dict", self.default_config["scale_dict"])
        self.offset_dict = self.config.get("offset_dict", self.default_config["offset_dict"])

        # ---------- 窗口属性 ----------
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # ---------- 画布 ----------
        self.canvas = QLabel(self)
        self.canvas.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)

        # ---------- 状态 ----------
        self.actions = ["idle", "stuck", "sleeping", "bark", "fly", "dive", "floating", "shake", "struggle"]
        self.state = self.config.get("default_state", "fly")
        self.default_state = self.config.get("default_state", "fly")
        self.current_frame_index = 0
        self.last_bark_time = 0
        self.fly_idle_timer = None

        # ---------- 声音 ----------
        self.sound_dict = {}           # action -> path OR action -> [paths] for bark
        self.ephemeral_sounds = []     # 短期引用，防止被回收
        self.loop_sound = None
        self.prev_volume = self.config["volume"].get("prev_volume", 20)
        self.mute_on_start = self.config["volume"].get("mute_on_start", False)

        # ---------- 帧缓存 ----------
        self.frames_orig = {}
        self.frames_mirror = {}
        self.transition_frames_orig = {}
        self.transition_frames_mirror = {}

        # ---------- 交互 ----------
        self.mouse_inside = False
        self.drag_position = QPoint()
        self.facing_left = False
        self.facing_actions = {"fly", "bark"}
        self.local_anim_running = False
        self.local_anim_cancel = False

        # 初始化大小以容纳最大缩放
        max_scale = max(self.scale_dict.values())
        self.resize(int(self.base_width * max_scale), int(self.base_height * max_scale))

        # ---------- 资源加载 ----------
        self._load_sounds()
        self._load_frames()
        self._load_transitions()

        # ---------- 全局定时器 ----------
        self.global_timer = QTimer(self)
        self.global_timer.timeout.connect(self._global_tick)
        self.global_timer.start(self.FRAME_MS)

        # ---------- fly->idle & idle->sleep 定时器 ----------
        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self._fly_to_idle)

        self.idle_sleep_timer = QTimer(self)
        self.idle_sleep_timer.setSingleShot(True)
        self.idle_sleep_timer.timeout.connect(self._idle_to_sleep)

        # ---------- 音量控件 ----------
        self.volume_widget = None
        self.mute_button = None
        self.volume_slider = None
        self.close_timer = None

        # ---------- 恢复位置 ----------
        pos_x = self.config.get("position", {}).get("x")
        pos_y = self.config.get("position", {}).get("y")
        if pos_x is not None and pos_y is not None:
            self.move(pos_x, pos_y)

        # ---------- 启动循环音 ----------
        self._start_loop_sound(self.state)

    # ================== CONFIG SAVE ==================
    def save_config(self):
        # 音量
        self.config["volume"]["prev_volume"] = self.prev_volume
        self.config["volume"]["mute_on_start"] = self.mute_button.isChecked() if self.mute_button else self.mute_on_start
        # 位置
        self.config["position"]["x"] = self.x()
        self.config["position"]["y"] = self.y()
        # 写入文件
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def closeEvent(self, event):
        self.save_config()
        event.accept()

    # ----------------- 资源加载 -----------------
    def _load_sounds(self):
        """加载声效路径；bark 支持文件夹内多个 wav"""
        for action in self.actions:
            if action == "bark":
                bark_dir = os.path.join(base_path, "wav", "bark")
                if os.path.isdir(bark_dir):
                    files = sorted([os.path.join(bark_dir, f) for f in os.listdir(bark_dir) if f.lower().endswith(".wav")])
                    self.sound_dict["bark"] = files
                else:
                    self.sound_dict["bark"] = []
            else:
                path = os.path.join(base_path, "wav", f"{action}.wav")
                self.sound_dict[action] = path if os.path.exists(path) else None

    def _load_frames(self):
        """加载每个动作的原始帧并生成镜像帧（延迟在加载时完成，避免每帧变换开销）。"""
        for action in self.actions:
            folder = os.path.join(base_path, "png", action)
            frames = []
            if os.path.isdir(folder):
                for fname in sorted(os.listdir(folder)):
                    if fname.lower().endswith(".png"):
                        frames.append(QPixmap(os.path.join(folder, fname)))
            self.frames_orig[action] = frames
            # 预生成镜像版本
            self.frames_mirror[action] = [pix.transformed(QTransform().scale(-1, 1)) for pix in frames]

        # 确保当前 frames 指向存在的列表，避免空列表导致索引错误
        if not self.frames_orig.get(self.state):
            for a in self.actions:
                if self.frames_orig.get(a):
                    self.state = a
                    break

    def _load_transitions(self):
        trans_root = os.path.join(base_path, "png", "transition")
        if not os.path.isdir(trans_root):
            return
        for folder in sorted(os.listdir(trans_root)):
            folder_path = os.path.join(trans_root, folder)
            if not os.path.isdir(folder_path):
                # 单帧 flip.png 特殊处理
                if folder.lower() == "flip.png":
                    pix = QPixmap(folder_path)
                    if not pix.isNull():
                        self.transition_frames_orig[("fly", "flip")] = [pix]
                        self.transition_frames_mirror[("fly", "flip")] = [pix.transformed(QTransform().scale(-1, 1))]
                continue
            # 原有多帧逻辑...
            name = folder.lower()
            parts = name.split("_to_") if "_to_" in name else name.split("_")
            if len(parts) >= 2:
                from_state = parts[0]
                to_state = parts[1]
                frames = []
                for f in sorted(os.listdir(folder_path)):
                    if f.lower().endswith(".png"):
                        frames.append(QPixmap(os.path.join(folder_path, f)))
                if frames:
                    self.transition_frames_orig[(from_state, to_state)] = frames
                    self.transition_frames_mirror[(from_state, to_state)] = [
                        pix.transformed(QTransform().scale(-1, 1)) for pix in frames
                    ]

    # ----------------- 声音控制 -----------------
    def _start_loop_sound(self, action):
        """开始循环音效（非 bark）。会停止上一个循环音。"""
        if self.loop_sound:
            try:
                self.loop_sound.stop()
            except Exception:
                pass
            self.loop_sound = None

        path = self.sound_dict.get(action)
        if not path or isinstance(path, list):
            return
        s = QSoundEffect()
        s.setSource(QUrl.fromLocalFile(path))
        s.setLoopCount(QSoundEffect.Infinite)
        s.setVolume(self.prev_volume / 100)
        s.play()
        self.loop_sound = s

    def _play_ephemeral_sound(self, path):
        """播放一次性声音并短期保存引用以防被回收。自动清理引用（5s）。"""
        if not path:
            return
        s = QSoundEffect()
        s.setSource(QUrl.fromLocalFile(path))
        s.setLoopCount(1)
        s.setVolume(self.prev_volume / 100)
        s.play()
        self.ephemeral_sounds.append(s)

        # 清理引用（5秒后）
        QTimer.singleShot(5000, lambda: self._cleanup_ephemeral(s))

    def _cleanup_ephemeral(self, s):
        try:
            self.ephemeral_sounds.remove(s)
        except ValueError:
            pass

    # ----------------- 帧显示与全局循环 -----------------
    def _global_tick(self):
        """全局循环：用于默认动作（非局部动画时）"""
        if self.local_anim_running:
            return  # 若局部动画正在跑，全局循环暂停
        frames = self._frames_for_state(self.state)
        if not frames:
            return
        # 每帧都实时决定朝向（fly 需要每帧更新朝向）
        if self.state in ("fly",):
            self._update_facing()
        # safe index
        if self.current_frame_index >= len(frames):
            self.current_frame_index = 0
        pix = frames[self.current_frame_index]
        self._show_pixmap(pix, self.state)
        self.current_frame_index = (self.current_frame_index + 1) % len(frames)

    def _show_pixmap(self, pixmap: QPixmap, state_for_scale: str, x_offset: int = 0):
        """缩放并显示 pixmap（按 state 的 scale），可选水平偏移"""
        scale = self.scale_dict.get(state_for_scale, 1.0)
        new_w = int(self.base_width * scale)
        new_h = int(self.base_height * scale)
        if not pixmap.isNull():
            pm = pixmap.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.canvas.setPixmap(pm)
            self.canvas.resize(pm.size())

            # 查 offset_dict，找不到就默认 0
            y_offset = self.offset_dict.get(state_for_scale, 0)

            # sleeping 状态自动横向偏移 ±27px
            if state_for_scale == "sleeping":
                x_offset = -27 if not self._is_facing_left() else 27
                y_offset += 5

            self.canvas.move(
                (self.width() - pm.width()) // 2 + x_offset,
                self.height() - pm.height() + y_offset
            )


    def _frames_for_state(self, state):
        """根据当前朝向选择原始或镜像帧集合"""
        if self._is_facing_left():
            return self.frames_mirror.get(state, [])
        else:
            return self.frames_orig.get(state, [])

    def _is_facing_left(self):
        """判断当前是否应面向左（用于选择镜像帧）"""
        return getattr(self, "facing_left", False)

    # ----------------- 局部动画（过渡 / bark / 其它） -----------------
    def _play_frame_sequence(self, frames, per_frame_callback=None, on_complete=None, 
                            dynamic_orientation=False, state_for_scale=None):
        """
        播放 frames 序列（局部动画），最后一帧显示至少一帧时间后再触发 on_complete，
        避免最后一帧卡顿或不显示。
        """
        if not frames:
            if on_complete:
                on_complete()
            return

        if self.local_anim_running:
            self.local_anim_cancel = True
            QTimer.singleShot(self.FRAME_MS, lambda: self._play_frame_sequence(
                frames, per_frame_callback, on_complete, dynamic_orientation, state_for_scale))
            return

        self.local_anim_cancel = False
        self.local_anim_running = True
        self.global_timer.stop()

        idx = 0
        total = len(frames)

        def _next():
            nonlocal idx
            if self.local_anim_cancel:
                self.local_anim_running = False
                self.global_timer.start(self.FRAME_MS)
                return

            # 显示当前帧
            pix = frames[idx]
            if dynamic_orientation and self._is_facing_left():
                pix = pix.transformed(QTransform().scale(-1, 1))

            self._show_pixmap(pix, state_for_scale if state_for_scale else self.state)

            if per_frame_callback:
                per_frame_callback(idx)

            idx += 1

            if idx < total:
                # 普通帧：继续下一帧
                QTimer.singleShot(self.FRAME_MS, _next)
            else:
                # 最后一帧：保证显示一帧时间，再触发完成回调
                QTimer.singleShot(self.FRAME_MS, lambda: (
                    on_complete() if on_complete else None,
                    setattr(self, 'local_anim_running', False),
                    self.global_timer.start(self.FRAME_MS)
                ))

        _next()

    def stop_local_animation(self):
        """外部调用可请求中断正在播放的局部动画（例如 mouseRelease 时）"""
        if self.local_anim_running:
            self.local_anim_cancel = True
        else:
            # 确保全局循环在非本地动画时正在运行
            if not self.global_timer.isActive():
                self.global_timer.start(self.FRAME_MS)

    # ----------------- 公共动作接口 -----------------
    def change_state(self, new_state):
        if new_state == self.state:
            return
        # 若要切换到 bark，请走 play_bark（包含冷却与声音）
        if new_state == "bark":
            self.play_bark()
            return

        self.state = new_state
        self.current_frame_index = 0
        self._start_loop_sound(new_state)

    def play_bark(self):
        """触发 bark：冷却 + 声音逻辑 + 动画"""
        now = int(time.time() * 1000)
        if now - self.last_bark_time < self.bark_cooldown:
            return
        # 如果已有局部动画在跑，拒绝新的 bark（防止叠加闪烁）
        if self.local_anim_running:
            return
        self.last_bark_time = now

        # 确定触发时的朝向（鼠标进入时按进入方向）
        self._update_facing_from_cursor()

        # 先播放 bark 音（短促、ephemeral）
        bark_files = self.sound_dict.get("bark", [])
        if bark_files:
            # play ephemeral bark sound (does not stop loop_sound)
            self._play_ephemeral_sound(random.choice(bark_files))

        if self.state == "fly":
            # 如果正在 fly：不要停止 fly 的循环音，只播放 bark 动画（不打断 fly 音）
            frames = self.frames_mirror["bark"] if self._is_facing_left() else self.frames_orig["bark"]
            # state_for_scale 设置为 'bark'，确保缩放按 bark 的 scale 生效
            self._play_frame_sequence(frames, dynamic_orientation=False, on_complete=lambda: None, state_for_scale="bark")
            return
        else:
            # 非 fly：停止当前循环音（若有），并补一段 'fly' 音效（ephemeral）以营造叫完立即飞的感觉
            if self.loop_sound:
                try:
                    self.loop_sound.stop()
                except Exception:
                    pass
            self.loop_sound = None
            fly_path = self.sound_dict.get("fly")
            if fly_path:
                self._play_ephemeral_sound(fly_path)

        # 播放 bark 动画 -> 结束后过渡到 fly
        bark_frames = self.frames_mirror["bark"] if self._is_facing_left() else self.frames_orig["bark"]
        # 确保缩放按 bark 生效：state_for_scale="bark"
        self._play_frame_sequence(bark_frames, dynamic_orientation=False, on_complete=self._after_bark, state_for_scale="bark")

    def _after_bark(self):
        self.state = "fly"
        self.current_frame_index = 0
        self._start_loop_sound("fly")

    def play_struggle_to_fly(self):
        """触发 struggle -> fly 过渡
        仅在 mouseRelease 时调用（若当前状态为 struggle）。
        """
        self.state = "fly"
        self.current_frame_index = 0

        # 获取 struggle->fly 的 transition 帧
        trans_frames = self.transition_frames_orig.get(("struggle", "fly"))
        if not trans_frames:
            # 没有 transition 直接回到 fly 循环
            if not self.global_timer.isActive():
                self.global_timer.start(self.FRAME_MS)
            return

        def after_transition():
            # transition 播放完成后恢复 fly 循环显示
            self.local_anim_running = False
            if not self.global_timer.isActive():
                self.global_timer.start(self.FRAME_MS)
                

        # 播放 transition，dynamic_orientation=False，state_for_scale="fly"
        self._play_frame_sequence(
            trans_frames,
            dynamic_orientation=False,
            on_complete=after_transition,
            state_for_scale="fly"
        )
        self._start_loop_sound("fly")
    
    def _enter_idle(self):
        """进入 idle 状态，并启动 idle→sleep 计时器（如果鼠标不在窗口）"""
        self.state = "idle"
        self.current_frame_index = 0

        if not self.global_timer.isActive():
            self.global_timer.start(self.FRAME_MS)

        # 如果鼠标在外面，1 秒后触发 sleep
        if not self.mouse_inside:
            self.idle_sleep_timer.start(self.idle_sleep_delay)


    def _fly_to_idle(self):
        if self.state != "fly":
            return

        trans_frames = self.transition_frames_orig.get(("fly", "idle"))
        if not trans_frames:
            self._enter_idle()
            return

        def after_transition():
            self._enter_idle()

        # 播放 transition，保持朝向
        self._play_frame_sequence(
            trans_frames,
            dynamic_orientation=True,
            on_complete=after_transition,
            state_for_scale="idle"
        )

        # 淡出 fly 循环音
        if self.loop_sound:
            self._fade_out_sound(self.loop_sound, duration=500)  # 500ms 淡出
            self.loop_sound = None
   
    def _enter_sleeping(self):
        """进入 sleeping 状态"""
        self.state = "sleeping"
        self.current_frame_index = 0
        if not self.global_timer.isActive():
            self.global_timer.start(self.FRAME_MS)
        self._start_loop_sound("sleeping")



    def _idle_to_sleep(self):
        """idle -> sleeping，过渡沿用 idle 朝向，最终 sleeping 朝向与 idle 相反"""
        if self.state != "idle" or self.mouse_inside:
            return

        trans_frames = self.transition_frames_orig.get(("idle", "sleeping"))
        idle_facing = self.facing_left  # 记录当前 idle 朝向

        if not trans_frames:
            # 没有过渡帧就直接睡眠
            self.facing_left = not idle_facing  # sleeping 方向与 idle 相反
            self._enter_sleeping()
            return

        def after_transition():
            # 过渡完成后，sleeping 朝向与 idle 相反
            self.facing_left = not idle_facing
            self._enter_sleeping()

        # 播放过渡帧，dynamic_orientation=True 使用 idle 朝向
        self._play_frame_sequence(
            trans_frames,
            dynamic_orientation=True,
            on_complete=after_transition,
            state_for_scale="idle"  # 缩放沿用 idle
        )

    def _fade_out_sound(self, sound: QSoundEffect, duration=500):
        """让音效在 duration 毫秒内淡出"""
        steps = 10
        interval = duration // steps
        volume_step = sound.volume() / steps

        def reduce_volume():
            vol = max(0.0, sound.volume() - volume_step)
            sound.setVolume(vol)
            if vol <= 0.0:
                sound.stop()
                timer.stop()
                timer.deleteLater()

        timer = QTimer(self)
        timer.timeout.connect(reduce_volume)
        timer.start(interval)


    # ----------------- 朝向（鼠标） -----------------
    def _update_facing(self):
        if self.state not in self.facing_actions or self.local_anim_running:
            return
        cursor_x = QCursor.pos().x()
        pet_center_x = self.x() + self.width() // 2
        new_left = cursor_x < pet_center_x
        if new_left != self.facing_left:
            # flip transition
            trans = self.transition_frames_orig.get((self.state, "flip"))
            if trans:
                def after_flip():
                    self.facing_left = new_left
                self._play_frame_sequence(
                    trans,
                    dynamic_orientation=False,
                    on_complete=after_flip,
                    state_for_scale="fly"   # 缩放仍按 fly
                )
            else:
                self.facing_left = new_left



    def _update_facing_from_cursor(self):
        """在触发（enter）时设置朝向（用于 bark 触发时的面向）。"""
        cursor_x = QCursor.pos().x()
        pet_center_x = self.x() + self.width() // 2
        self.facing_left = cursor_x < pet_center_x

    # ----------------- UI 事件 -----------------
    def enterEvent(self, event):
        if self.leave_timer.isActive():
            self.leave_timer.stop()
        if self.idle_sleep_timer.isActive():
            self.idle_sleep_timer.stop()

        self.mouse_inside = True
        if self.state != "sleeping":
            self._update_facing_from_cursor()
            self.play_bark()
        event.accept()


    def leaveEvent(self, event):
        self.mouse_inside = False
        if self.state != "sleeping":
            # 重新启动离开计时器
            self.leave_timer.start(self.leave_delay)
        event.accept()





    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 记录拖拽偏移
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            # 左键按下时触发挣扎动作
            self.change_state("struggle")
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPos() - self.drag_position)
            # 拖拽时也同步更新音量控件位置
            if self.volume_widget and self.volume_widget.isVisible():
                x = self.x() + (self.width() - self.volume_widget.width()) // 2
                y = self.y() + self.height()
                self.volume_widget.move(x, y)
            event.accept()

    # ----------------- 鼠标释放事件 -----------------
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.state == "struggle":
                # 播放松开动画
                self.play_struggle_to_fly()

            else:
                self.stop_local_animation()
                self.change_state(self.default_state)
            self.snap_to_taskbar()
            event.accept()

    # ----------------- 音量/控件（保留原接口） -----------------
    def show_volume_widget(self):
        if self.volume_widget and self.volume_widget.isVisible():
            self.volume_widget.close()
            return
        self.volume_widget = QWidget(self, Qt.Tool | Qt.FramelessWindowHint)
        self.volume_widget.resize(200, 40)
        self.volume_widget.setStyleSheet("QWidget { background-color: rgba(255,255,255,0.85); border-radius: 8px; }")
        layout = QHBoxLayout(self.volume_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.mute_button = QPushButton()
        self.mute_button.setCheckable(True)
        self.mute_button.setIcon(QIcon(os.path.join(base_path, "icons", "volume.png")))
        self.mute_button.setFixedSize(24, 24)
        self.mute_button.clicked.connect(self._toggle_mute)
        layout.addWidget(self.mute_button)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.prev_volume)
        self.volume_slider.valueChanged.connect(self._change_volume)
        layout.addWidget(self.volume_slider)

        self.volume_widget.show()
        x = self.x() + (self.width() - self.volume_widget.width()) // 2
        y = self.y() + self.height()
        self.volume_widget.move(x, y)
        self.volume_widget.installEventFilter(self)

    def _toggle_mute(self):
        if self.mute_button.isChecked():
            self.prev_volume = self.volume_slider.value()
            if self.loop_sound:
                self.loop_sound.setVolume(0)
            self.volume_slider.setValue(0)
        else:
            self.volume_slider.setValue(self.prev_volume)
            if self.loop_sound:
                self.loop_sound.setVolume(self.prev_volume / 100)

    def _change_volume(self, value):
        if self.loop_sound:
            self.loop_sound.setVolume(value / 100)
        for s in list(self.ephemeral_sounds):
            try:
                s.setVolume(value / 100)
            except Exception:
                pass
        self.prev_volume = value

    def eventFilter(self, obj, event):
        if obj == self.volume_widget:
            if event.type() == QEvent.Enter:
                # 鼠标回来，取消关闭
                if self.close_timer:
                    self.close_timer.stop()
                    self.close_timer = None

            elif event.type() == QEvent.Leave:
                # 鼠标离开，3 秒后关闭
                if self.close_timer:
                    self.close_timer.stop()
                self.close_timer = QTimer(self)
                self.close_timer.setSingleShot(True)
                self.close_timer.timeout.connect(self._close_volume_widget)
                self.close_timer.start(1500) # 1.5 秒
        return super().eventFilter(obj, event)

    def _close_volume_widget(self):
        if self.volume_widget:
            self.volume_widget.close()
            self.volume_widget = None


    # ----------------- 任务栏吸附 -----------------
    def snap_to_taskbar(self): # 获取屏幕可用区域（排除任务栏） 
        screen_geom = QApplication.primaryScreen().availableGeometry() 
        screen_bottom = screen_geom.bottom() # 可用区域底部（任务栏上沿） 
        pet_bottom = self.y() + self.height() # 如果宠物底部低于或靠近可用区域底部 
        if pet_bottom >= screen_bottom - 5: # 小余量防止跳动 # 把宠物底部直接贴到可用区域底部 
            self.move(self.x(), screen_bottom - self.height() + 5)

        
    # ----------------- 右键菜单 -----------------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("卡住").triggered.connect(lambda: self.change_state("stuck"))
        menu.addAction("挣扎").triggered.connect(lambda: self.change_state("struggle"))
        menu.addAction("飞").triggered.connect(lambda: self.change_state("fly"))
        menu.addAction("叫").triggered.connect(self.play_bark)
        menu.addAction("闲置").triggered.connect(lambda: self.change_state("idle"))
        menu.addAction("睡觉").triggered.connect(lambda: self.change_state("sleeping"))
        menu.addAction("音量调节").triggered.connect(self.show_volume_widget)
        menu.addAction("退出").triggered.connect(QApplication.quit)
        menu.exec_(event.globalPos())


# --------- 启动 ----------
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"[Info] Current working directory set to {script_dir}")

    app = QApplication(sys.argv)
    try:
        pet = DesktopPet()
        pet.show()
        sys.exit(app.exec_())
    except Exception as e:
        print("[Error] Exception during DesktopPet execution:", e)
        sys.exit(1)

