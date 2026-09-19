# 1. Python environment set up kar raha hai
FROM python:3.12-slim

# 2. Python logs ko real-time terminal pe dikhane ke liye
ENV PYTHONUNBUFFERED=1

# 3. Server ke andar folder ka naam
WORKDIR /app

# 4. requirements.txt copy karke saari libraries install karega
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 5. Aapka poora Django code container ke andar copy karega
COPY . /app/

# 6. Django server ka port expose kar raha hai
EXPOSE 8000

# 7. Production server (Gunicorn) ko s
CMD ["sh", "-c", "python manage.py migrate && gunicorn weathervibe.wsgi:application --bind 0.0.0.0:8000"]