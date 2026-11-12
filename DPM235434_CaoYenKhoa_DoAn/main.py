import network
import usocket as socket
import ujson as json
import time
import sys
import os
import hashlib
import ubinascii
from machine import Pin, PWM

# ==================== CẤU HÌNH SINRIC PRO & WIFI ====================
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASS = ""

APP_KEY = "23465334-dcaf-4efb-83b1-beb0c0f238a2".strip()
APP_SECRET = "13fadd6d-4c9d-476f-bba5-90b1eaf45ab6-c30b0f10-47ad-415a-8fd8-8ff54e5974df".strip()
DEVICE_ID = "6ad1a4a5ab63d1bf9fbfef18".strip()

# ==================== CẤU HÌNH PHẦN CỨNG ====================
RELAY_PIN = 2
relay = Pin(RELAY_PIN, Pin.OUT)
relay.value(0)

BUTTON_PIN = 4
btn = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

pwm_r = PWM(Pin(14), freq=1000); pwm_r.duty(0)
pwm_g = PWM(Pin(12), freq=1000); pwm_g.duty(0)
pwm_b = PWM(Pin(13), freq=1000); pwm_b.duty(0)

current_brightness = 100
current_color = {"r": 255, "g": 255, "b": 255}
current_color_temp = None  # Kelvin gan nhat; None neu dang chon RGB truc tiep

btn_pressed_flag = False
last_btn_time = 0

# ==================== BIẾN BẢO VỆ FLASH ====================
need_save_flash = False
last_change_time = 0

# In trang thai theo mot mau thong nhat
def show_status(source, detail=""):
    state = "BAT" if relay.value() else "TAT"
    visible = "SANG" if relay.value() and current_brightness > 0 and any(current_color.values()) else "TAT"
    msg = "[{}] Den: {} | LED: {} | Do sang: {}% | RGB: ({},{},{})".format(
        source, state, visible, current_brightness,
        current_color["r"], current_color["g"], current_color["b"])
    if current_color_temp is not None:
        msg += " | Nhiet do mau: {}K".format(current_color_temp)
    if detail:
        msg += " | " + detail
    print(msg)

def clamp(value, max_value):
    return max(0, min(max_value, int(value)))

def restore_brightness_on_activation():
    """Den sap sang: neu do sang cu la 0% thi phuc hoi 100%."""
    global current_brightness, pending_brightness_sync
    if current_brightness != 0:
        return False
    current_brightness = 100
    pending_brightness_sync = True
    return True

def btn_handler(pin):
    global btn_pressed_flag, last_btn_time
    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_btn_time) > 250:
        btn_pressed_flag = True
        last_btn_time = current_time

btn.irq(trigger=Pin.IRQ_FALLING, handler=btn_handler)

# ==================== LƯU TRỮ BỘ NHỚ FLASH ====================
STATE_FILE = "state.json"

def request_save_state():
    """Chỉ đánh dấu là cần lưu, chưa ghi ngay để tránh hỏng Flash"""
    global need_save_flash, last_change_time
    need_save_flash = True
    last_change_time = time.ticks_ms()

def commit_save_state():
    """Thực sự ghi vào Flash (được gọi ở vòng lặp chính sau khi trễ 3s)"""
    state = {
        "brightness": current_brightness,
        "color": current_color,
        "power": relay.value(),
        "colorTemperature": current_color_temp
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        return True
    except Exception as e:
        print("[FLASH] Loi ghi:", e)
        return False

def load_state():
    """Đọc trạng thái cũ khi mất điện có lại"""
    global current_brightness, current_color, current_color_temp
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        b = clamp(state.get("brightness", 100), 100)
        c = state.get("color", {})
        rgb = {k: clamp(c.get(k, 255), 255) for k in ("r", "g", "b")}
        temp = state.get("colorTemperature")
        current_brightness = b
        current_color = rgb
        current_color_temp = int(temp) if temp is not None else None
        relay.value(clamp(state.get("power", 0), 1))
    except Exception:
        # Chay lan dau hoac file khong hop le: dung gia tri mac dinh.
        current_brightness = 100
        current_color = {"r": 255, "g": 255, "b": 255}
        current_color_temp = None
        relay.value(0)

# ==================== HÀM TIỆN ÍCH & MẠNG ====================
# ==================== KÝ BẢN TIN & ĐỒNG BỘ THỜI GIAN (SINRIC PRO) ====================
unix_base = 0
tick_base = 0
clock_synced = False
pending_sync = True
pending_brightness_sync = False

def set_clock(unix_ts):
    global unix_base, tick_base, clock_synced
    unix_base = int(unix_ts)
    tick_base = time.ticks_ms()
    clock_synced = True

def now_unix():
    return unix_base + time.ticks_diff(time.ticks_ms(), tick_base) // 1000

def try_ntp():
    try:
        import ntptime
        ntptime.settime()
        t = time.time()
        if t < 1600000000:
            t += 946684800
        set_clock(t)
    except Exception:
        pass  # Sinric se gui thoi gian khi ket noi.

def hmac_sha256(key, msg):
    if len(key) > 64:
        key = hashlib.sha256(key).digest()
    key = key + b'\x00' * (64 - len(key))
    o_pad = bytes([b ^ 0x5c for b in key])
    i_pad = bytes([b ^ 0x36 for b in key])
    return hashlib.sha256(o_pad + hashlib.sha256(i_pad + msg).digest()).digest()

def sign_payload(payload_str):
    mac = hmac_sha256(APP_SECRET.encode('utf-8'), payload_str.encode('utf-8'))
    return ubinascii.b2a_base64(mac).decode().strip()

def dumps_compact(o):
    """JSON gọn (không dấu cách) để chuỗi ký và chuỗi gửi đi giống hệt nhau"""
    if o is True: return "true"
    if o is False: return "false"
    if o is None: return "null"
    if isinstance(o, str): return json.dumps(o)
    if isinstance(o, (int, float)): return str(o)
    if isinstance(o, dict):
        return "{" + ",".join(json.dumps(str(k)) + ":" + dumps_compact(v) for k, v in o.items()) + "}"
    return json.dumps(o)

def new_token():
    return ubinascii.hexlify(os.urandom(16)).decode()

def send_signed(sock, payload):
    if not clock_synced:
        print("[CẢNH BÁO] Chưa có đồng hồ, không thể gửi bản tin có chữ ký.")
        return False
    payload["createdAt"] = now_unix()
    p = dumps_compact(payload)
    msg = ('{"header":{"payloadVersion":2,"signatureVersion":1},"payload":' + p +
           ',"signature":{"HMAC":"' + sign_payload(p) + '"}}')
    return send_ws_message(sock, msg)

def send_response(sock, action, req_payload, value):
    send_signed(sock, {
        "action": action,
        "clientId": req_payload.get("clientId", "portal"),
        "deviceId": DEVICE_ID,
        "message": "OK",
        "replyToken": req_payload.get("replyToken", ""),
        "success": True,
        "type": "response",
        "value": value
    })

def send_event(sock, action, value):
    return send_signed(sock, {
        "action": action,
        "cause": {"type": "PHYSICAL_INTERACTION"},
        "deviceId": DEVICE_ID,
        "replyToken": new_token(),
        "type": "event",
        "value": value
    })

def power_text():
    return "On" if relay.value() else "Off"

def send_ws_message(sock, payload_str):
    """Gui JSON qua WebSocket, su dung cung giao thuc voi ban goc."""
    payload = payload_str.encode('utf-8')
    length = len(payload)
    if length >= 65536:
        raise ValueError("Ban tin WebSocket qua dai")

    # Client phai mask payload theo chuan WebSocket.
    mask = os.urandom(4)
    if length < 126:
        header = bytes([0x81, 0x80 | length])
    else:
        header = bytes([0x81, 0xFE, (length >> 8) & 255, length & 255])
    encoded = bytes(payload[i] ^ mask[i % 4] for i in range(length))
    data = header + mask + encoded

    # Socket non-blocking co the gui mot phan, can gui het frame.
    offset = 0
    start = time.ticks_ms()
    while offset < len(data):
        try:
            n = sock.send(data[offset:])
            if n is None:
                n = len(data) - offset
            if n > 0:
                offset += n
        except OSError as e:
            if not e.args or e.args[0] not in (11, 35):
                raise
        if time.ticks_diff(time.ticks_ms(), start) > 1500:
            raise OSError("Gui WebSocket qua thoi gian")
        if offset < len(data):
            time.sleep_ms(10)
    return True

def extract_frames(buf):
    """Tách tất cả khung WebSocket đã nhận đủ trong bộ đệm. Trả về (danh sách tin, phần dư)"""
    msgs = []
    while len(buf) >= 2:
        opcode = buf[0] & 0x0F
        masked = buf[1] & 0x80
        plen = buf[1] & 0x7F
        idx = 2
        if plen == 126:
            if len(buf) < 4: break
            plen = (buf[2] << 8) | buf[3]
            idx = 4
        elif plen == 127:
            if len(buf) < 10: break
            plen = int.from_bytes(buf[2:10], 'big')
            idx = 10
        if masked: idx += 4
        if len(buf) < idx + plen: break          
        payload = buf[idx:idx + plen]
        buf = buf[idx + plen:]
        if opcode == 0x01:
            try: msgs.append(payload.decode('utf-8'))
            except Exception: pass
        elif opcode == 0x09: msgs.append("PING")
        elif opcode == 0x08: msgs.append("CLOSE")
    return msgs, buf

def connect_wifi():
    """Ket noi Wi-Fi theo cach cua code cu, khong reset interface lien tuc."""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        time.sleep(1)

        if wlan.isconnected():
            return True

        print("[WIFI] Dang ket noi {}...".format(WIFI_SSID))
        wlan.connect(WIFI_SSID, WIFI_PASS)

        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            handle_button()
            save_if_needed()
            time.sleep(0.5)
            timeout -= 1

        if wlan.isconnected():
            print("[WIFI] Da ket noi | IP:", wlan.ifconfig()[0])
            wait_local(2000)
            return True

        print("[WIFI] Chua nhan IP | Status:", wlan.status())
        print("[WIFI] Se thu lai, khong tat giao dien Wi-Fi")
        return False

    except Exception as err:
        print("[WIFI] Loi ket noi:", err)
        return False

def handle_button(client=None):
    global btn_pressed_flag, pending_sync
    if not btn_pressed_flag:
        return
    btn_pressed_flag = False
    relay.value(1 - relay.value())
    restored = False
    if relay.value() == 1:
        restored = restore_brightness_on_activation()
    apply_color_and_brightness()
    request_save_state()
    show_status("NUT NHAN", "Khoi phuc do sang 100%" if restored else "Bat/tat den")
    pending_sync = True
    if client is not None and clock_synced:
        if send_event(client, "setPowerState", {"state": power_text()}):
            pending_sync = False


def save_if_needed():
    global need_save_flash, last_change_time
    if need_save_flash and time.ticks_diff(time.ticks_ms(), last_change_time) >= 3000:
        if commit_save_state():
            need_save_flash = False
        else:
            last_change_time = time.ticks_ms()


def wait_local(delay_ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < delay_ms:
        handle_button()
        save_if_needed()
        time.sleep_ms(50)

def apply_color_and_brightness():
    if relay.value() == 0:
        pwm_r.duty(0); pwm_g.duty(0); pwm_b.duty(0)
        return
        
    factor = current_brightness / 100.0
    r_val = current_color["r"] * factor
    g_val = current_color["g"] * factor
    b_val = current_color["b"] * factor
    
    pwm_r.duty(int((r_val / 255.0) * 1023))
    pwm_g.duty(int((g_val / 255.0) * 1023))
    pwm_b.duty(int((b_val / 255.0) * 1023))

def process_sinric_message(client, payload_str):
    global current_brightness, current_color, current_color_temp
    global pending_sync, pending_brightness_sync
    try:
        data = json.loads(payload_str)
        if "timestamp" in data:
            set_clock(data["timestamp"])
            return

        payload = data.get("payload", {})
        # Giu cach loc chi nhan request nhu phien ban da chay dung.
        if payload.get("type") != "request":
            # Neu Cloud bao loi, hien thi de co the chan doan.
            if payload.get("success") is False:
                print("[SINRIC] Cloud bao loi:", payload.get("message", "Khong ro ly do"))
            return
        if "createdAt" in payload:
            set_clock(payload["createdAt"])
        if payload.get("deviceId") != DEVICE_ID:
            return
        action = payload.get("action")
        val = payload.get("value", {})
        if not isinstance(val, dict):
            return

        if action == "setPowerState":
            state = str(val.get("state", "")).lower()
            if state not in ("on", "off"):
                return
            relay.value(1 if state == "on" else 0)
            restored = restore_brightness_on_activation() if relay.value() == 1 else False
            apply_color_and_brightness()
            pending_sync = False  # Lenh Cloud da la trang thai chinh thuc.
            show_status("CLOUD", "Bat/tat den | Khoi phuc do sang 100%" if restored else "Bat/tat den")
            answer = {"state": power_text()}

        elif action == "setColor":
            c = val.get("color", {})
            if not isinstance(c, dict):
                return
            current_color = {k: clamp(c.get(k, 255), 255) for k in ("r", "g", "b")}
            current_color_temp = None
            # Chon mau khi OFF chi luu mau, KHONG bat Relay.
            restored = restore_brightness_on_activation() if relay.value() == 1 else False
            apply_color_and_brightness()
            show_status("CLOUD", "Doi mau RGB | Khoi phuc do sang 100%" if restored else "Doi mau RGB")
            answer = {"color": current_color}

        elif action == "setBrightness":
            current_brightness = clamp(val.get("brightness", 100), 100)
            pending_brightness_sync = False
            apply_color_and_brightness()
            show_status("CLOUD", "Doi do sang")
            answer = {"brightness": current_brightness}

        elif action == "setColorTemperature":
            temp = int(val.get("colorTemperature", 4000))
            if temp < 1000 or temp > 10000:
                print("[CLOUD] Gia tri nhiet do mau khong hop le:", temp)
                return
            current_color_temp = temp
            if temp < 3500:
                current_color = {"r": 255, "g": 214, "b": 170}
            elif temp > 5500:
                current_color = {"r": 201, "g": 226, "b": 255}
            else:
                current_color = {"r": 255, "g": 255, "b": 255}
            # Doi nhiet do mau khi OFF van OFF. Neu ON ma do sang 0%, phuc hoi 100%.
            restored = restore_brightness_on_activation() if relay.value() == 1 else False
            apply_color_and_brightness()
            detail = "Nhan nhiet do mau: {}K".format(temp)
            if restored:
                detail += " | Khoi phuc do sang 100%"
            show_status("CLOUD", detail)
            answer = {"colorTemperature": temp}
        else:
            return

        request_save_state()
        send_response(client, action, payload, answer)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        print("[CLOUD] Du lieu khong hop le:", e)

# ==================== VÒNG LẶP CHÍNH ====================
def main():
    global pending_sync, pending_brightness_sync
    load_state()
    apply_color_and_brightness()
    show_status("KHOI DONG")

    while True:
        handle_button()
        save_if_needed()
        if not connect_wifi():
            wait_local(3000)
            continue
        if not clock_synced:
            try_ntp()
        print("[SINRIC] Dang ket noi Cloud...")
        client = None
        try:
            address = socket.getaddrinfo("ws.sinric.pro", 80)[0][-1]
            client = socket.socket()
            client.settimeout(5)
            client.connect(address)
            handshake_str = (
                "GET /v1 HTTP/1.1\r\nHost: ws.sinric.pro\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
                "appkey: {}\r\nappsecret: {}\r\ndeviceids: {}\r\n\r\n".format(APP_KEY, APP_SECRET, DEVICE_ID)
            )
            client.send(handshake_str.encode("utf-8"))
            response = client.recv(1024)
            if b" 101 " not in response.split(b"\r\n")[0]:
                raise OSError("Handshake bi tu choi: " + str(response[:70]))
            header_end = response.find(b"\r\n\r\n")
            rxbuf = response[header_end + 4:] if header_end >= 0 else b""
            client.setblocking(False)
            print("[SINRIC] Da ket noi Cloud thanh cong")
            show_status("TRANG THAI", "Sau khi ket noi")
            last_heartbeat = time.ticks_ms()
            pending_sync = True

            while True:
                handle_button(client)
                save_if_needed()
                if pending_sync and clock_synced:
                    if send_event(client, "setPowerState", {"state": power_text()}):
                        pending_sync = False
                if pending_brightness_sync and clock_synced:
                    if send_event(client, "setBrightness", {"brightness": current_brightness}):
                        pending_brightness_sync = False

                if time.ticks_diff(time.ticks_ms(), last_heartbeat) >= 15000:
                    client.send(b"\x89\x80\x00\x00\x00\x00")
                    last_heartbeat = time.ticks_ms()

                try:
                    raw_data = client.recv(2048)
                except OSError as e:
                    if e.args and e.args[0] in (11, 35):
                        raw_data = None
                    else:
                        raise
                if raw_data == b"":
                    raise OSError("May chu da dong ket noi")
                if raw_data:
                    rxbuf += raw_data
                if len(rxbuf) > 8192:
                    raise OSError("Bo dem WebSocket qua lon")
                msgs, rxbuf = extract_frames(rxbuf)
                for msg in msgs:
                    if msg == "CLOSE":
                        raise OSError("Cloud dong WebSocket")
                    elif msg == "PING":
                        client.send(b"\x8a\x80\x00\x00\x00\x00")
                    else:
                        process_sinric_message(client, msg)
                time.sleep_ms(50)
        except Exception as err:
            print("[SINRIC] Mat ket noi hoac khong ket noi duoc:", err)
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
        print("[SINRIC] Se thu ket noi lai sau 3 giay...")
        wait_local(3000)

main()