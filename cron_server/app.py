from apscheduler.schedulers.background import BackgroundScheduler
import requests
import time

def make_get_request_with_retry():
    url = '/sync-reminder-food-items-for-user/'
    max_retries = 5  # Maximum number of retries
    attempt = 1
    delay = 1  # Initial delay in seconds

    while attempt < max_retries:
        try:
            response = requests.get(url=url)
            if response.status_code == 200:
                print("GET request successful")
                return  # Exit the function if successful
            else:
                raise Exception("GET request failed")
        except Exception as e:
            print(f"Attempt {attempt}: {e}")
            attempt += 1
            if attempt == max_retries:
                print("Max retries reached. Exiting.")
            else:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2

# Create a scheduler
scheduler = BackgroundScheduler()

# Schedule the job to run every day at 9 AM
scheduler.add_job(make_get_request_with_retry, 'cron', hour=9, minute=0)

# Start the scheduler
scheduler.start()

# Keep the script running to allow the scheduler to execute the jobs
try:
    while True:
        pass
except KeyboardInterrupt:
    # Stop the scheduler if the script is interrupted
    scheduler.shutdown()
