import os
import sys
import telebot
import subprocess
import time
import threading
from telebot import types

TOKEN = '7604037815:AAG7iOgGmWwC8oE8vdrD4p997dr0CNKT3gA'  # حط توكن البوت هون
bot = telebot.TeleBot(TOKEN)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# uploaded_scripts: قائمة عناصر كل عنصر dict: {"id": idx, "filename": name, "auto_restart": True}
uploaded_scripts = []
running_processes = {}  # key = filename, value = subprocess.Popen
lock = threading.Lock()

def save_uploaded_file(file_bytes, filename):
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path

def start_script_by_name(filename):
    with lock:
        proc = running_processes.get(filename)
        # شغّل فقط إذا ما في عملية شغالة أو العملية انتهت
        if proc is None or proc.poll() is not None:
            try:
                path = os.path.join(UPLOAD_DIR, filename)
                running_processes[filename] = subprocess.Popen([sys.executable, path])
                return True, f"✅ تم تشغيل {filename}"
            except Exception as e:
                return False, f"❌ خطأ بتشغيل {filename}: {e}"
        else:
            return False, f"⚠️ {filename} شغّال بالفعل."

def stop_script_by_name(filename, kill_timeout=3):
    with lock:
        proc = running_processes.get(filename)
        if proc is None:
            return False, f"⚠️ {filename} غير شغّال."
        try:
            proc.terminate()
            # ننتظر قليلاً ثم نقتل لو ما توقف
            try:
                proc.wait(timeout=kill_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            del running_processes[filename]
            return True, f"🛑 تم إيقاف {filename}"
        except Exception as e:
            return False, f"❌ خطأ عند إيقاف {filename}: {e}"

def monitor_scripts():
    while True:
        with lock:
            # نعيد تشغيل فقط اللي auto_restart == True
            for item in uploaded_scripts:
                filename = item["filename"]
                auto = item.get("auto_restart", True)
                if not auto:
                    continue
                proc = running_processes.get(filename)
                path = os.path.join(UPLOAD_DIR, filename)
                # إذا الملف مفقود نتجاهل
                if not os.path.exists(path):
                    continue
                # لو ما في عملية أو العملية انتهت -> شغل
                if proc is None or proc.poll() is not None:
                    try:
                        running_processes[filename] = subprocess.Popen([sys.executable, path])
                        print(f"تم (re)تشغيل: {filename}")
                    except Exception as e:
                        print(f"فشل تشغيل {filename}: {e}")
        time.sleep(5)

# بناء لوحة لكل ملف
def make_file_markup():
    markup = types.InlineKeyboardMarkup()
    with lock:
        for idx, item in enumerate(uploaded_scripts):
            fn = item["filename"]
            auto = item.get("auto_restart", True)
            # أزرار: تشغيل - إيقاف - تبديل auto - حذف من القائمة (ما بحذف الملف فعلياً)
            row = [
                types.InlineKeyboardButton(f"▶️", callback_data=f"start|{idx}"),
                types.InlineKeyboardButton(f"🛑", callback_data=f"stop|{idx}"),
                types.InlineKeyboardButton(f"🔁{'ON' if auto else 'OFF'}", callback_data=f"toggleauto|{idx}"),
                types.InlineKeyboardButton(f"🗑️ إزالة", callback_data=f"remove|{idx}")
            ]
            markup.add(*row)
    # أزرار عامّة
    markup.add(types.InlineKeyboardButton("▶️ تشغيل الكل", callback_data="start_all"))
    markup.add(types.InlineKeyboardButton("🛑 إيقاف الكل", callback_data="stop_all"))
    return markup

@bot.message_handler(content_types=['document'])
def handle_bot_file(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = message.document.file_name

        if not file_name.endswith('.py'):
            bot.reply_to(message, "❌ فقط ملفات .py مقبولة.")
            return

        # حفظ الملف داخل مجلد uploads
        save_uploaded_file(downloaded_file, file_name)

        with lock:
            # إضافة للائحة مع auto_restart True بشكل افتراضي
            uploaded_scripts.append({"id": len(uploaded_scripts), "filename": file_name, "auto_restart": True})

        bot.reply_to(message, f"✅ تم رفع: {file_name}", reply_markup=make_file_markup())
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    data = call.data
    try:
        if data.startswith("start|"):
            idx = int(data.split("|",1)[1])
            with lock:
                if idx < 0 or idx >= len(uploaded_scripts):
                    bot.answer_callback_query(call.id, "ملف غير موجود.")
                    return
                filename = uploaded_scripts[idx]["filename"]
            ok, msg = start_script_by_name(filename)
            bot.send_message(call.message.chat.id, msg)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_file_markup())

        elif data.startswith("stop|"):
            idx = int(data.split("|",1)[1])
            with lock:
                if idx < 0 or idx >= len(uploaded_scripts):
                    bot.answer_callback_query(call.id, "ملف غير موجود.")
                    return
                filename = uploaded_scripts[idx]["filename"]
            ok, msg = stop_script_by_name(filename)
            bot.send_message(call.message.chat.id, msg)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_file_markup())

        elif data.startswith("toggleauto|"):
            idx = int(data.split("|",1)[1])
            with lock:
                if idx < 0 or idx >= len(uploaded_scripts):
                    bot.answer_callback_query(call.id, "ملف غير موجود.")
                    return
                uploaded_scripts[idx]["auto_restart"] = not uploaded_scripts[idx].get("auto_restart", True)
            bot.send_message(call.message.chat.id, f"🔁 حالياً: {'مفعّل' if uploaded_scripts[idx]['auto_restart'] else 'موقوف'} لإعادة التشغيل التلقائي.")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_file_markup())

        elif data.startswith("remove|"):
            idx = int(data.split("|",1)[1])
            with lock:
                if idx < 0 or idx >= len(uploaded_scripts):
                    bot.answer_callback_query(call.id, "ملف غير موجود.")
                    return
                filename = uploaded_scripts[idx]["filename"]
                # قبل الإزالة نوقفه لو شغال
                if filename in running_processes:
                    stop_script_by_name(filename)
                # إزالة من القائمة فقط (لا نحذف الملف من القرص)
                uploaded_scripts.pop(idx)
            bot.send_message(call.message.chat.id, f"🗑️ تمت إزالة {filename} من القائمة (الملف بقي في uploads/).")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_file_markup())

        elif data == "start_all":
            with lock:
                targets = [item["filename"] for item in uploaded_scripts]
            msgs = []
            for fn in targets:
                ok, m = start_script_by_name(fn)
                msgs.append(m)
            bot.send_message(call.message.chat.id, "\n".join(msgs))
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_file_markup())

        elif data == "stop_all":
            with lock:
                targets = list(running_processes.keys())
            msgs = []
            for fn in targets:
                ok, m = stop_script_by_name(fn)
                msgs.append(m)
            bot.send_message(call.message.chat.id, "\n".join(msgs) if msgs else "⚠️ لا توجد عمليات شغالة.")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_file_markup())

        else:
            bot.answer_callback_query(call.id, "زر غير معروف.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"حدث خطأ: {e}")

if __name__ == '__main__':
    monitor_thread = threading.Thread(target=monitor_scripts, daemon=True)
    monitor_thread.start()
    bot.infinity_polling()
