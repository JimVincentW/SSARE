FROM python:3.9

WORKDIR /app

# Copy the requirements.txt file
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the flows directory from the parent directory
COPY app/flows ./flows

# Copy the HTML templatesa & static files
COPY app/templates ./templates
COPY app/static ./static

# Copy the main.py file
COPY app/main.py .

# Copy the config.ini file
COPY app/config.ini .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
