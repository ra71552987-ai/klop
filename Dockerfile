# استخدم نسخة حديثة من PHP
FROM php:8.2-cli

# انسخ ملفات المشروع إلى داخل الحاوية
COPY . /app

# اجعل مجلد العمل هو /app
WORKDIR /app

# ثبّت أي إضافات ضرورية (مثل curl)
RUN docker-php-ext-install pcntl

# شغّل البوت
CMD ["php", "bot.php"]
