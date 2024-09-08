# TrelloBot

The TrelloBot project integrates Trello with Telegram!

## Key Features:

1. 🔔 Notifications for Managers:
   - Receive notifications when an employee completes a task.
   - Be informed when a comment is left.
   - Stay updated when a card's deadline is rescheduled.

2. 👥 Restricted Access for Employees:
   - Employees will have access only to the bot's functionality.
   - No access to the rest of the Trello board and others' tasks.

---

## Project Setup:

1. Clone the project:
    
      git clone https://github.com/carevvv/trello_bot

2. Webhooks:
   - The bot works with webhooks, requiring a personal web server for setup.

3. Install dependencies:
   
        pip install -r requirements.txt

5. Create a database and run the database creation script:
    
        python create_tables.py

6. Run the file:
    
        python bot.py
