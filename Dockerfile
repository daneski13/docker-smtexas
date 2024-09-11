FROM python:3.12.6-alpine3.20

# Set the working directory
WORKDIR /app

# Copy src files to the working directory
COPY /src .

# Copy requirements.txt to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN apk update && apk add --no-cache git
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
