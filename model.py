from peewee import *
import json

connection = SqliteDatabase('trello.db')
class BaseModel(Model):
    class Meta:
        database = connection


class Projects(BaseModel):
    tg_id = CharField()
    title = TextField(null=True)
    description = TextField(null=True)
    comments = TextField(null=True)  
    status = TextField()
    deadline = DateTimeField(null=True)

    def set_comments(self, data):
        self.comments = json.dumps(data)

    def get_comments(self):
        try:
            return json.loads(self.comments)
        except (TypeError, ValueError):
            return None

    class Meta:
        db_table = 'Projects'

class ProjectStatus(BaseModel):
    status_name = CharField(unique=True)

    class Meta:
        db_table = 'ProjectStatus'

class Notifications(BaseModel):
    tg_id = CharField()
    title = TextField()
    notification = BooleanField(default=False)
    last_notification_time = DateTimeField(null=True)
    reminder_message = TextField(null=True)

    class Meta:
        db_table = 'notifications'



def create_tables():
    with connection:
        connection.create_tables([Projects, Notifications, ProjectStatus])
    print('Таблицы созданы')



def clear_projects():
    with connection.atomic():
        Projects.delete().execute()

    with connection:
        connection.create_tables([Projects])


def update_projects(data):
    clear_projects()
    
    for item in data:
        add_project(item['tg_id'], item['title'], item['description'], item['comments'], item['status'], item['deadline'])


def add_project(tg_id, title, description, comments, status, deadline):
    with connection:
        Projects.create(tg_id=tg_id, title=title, description=description, 
                        comments=json.dumps(comments) if comments else None,
                        status=status, deadline=deadline)


def add_notification(tg_id, title):
    with connection:
        Notifications.create(tg_id = tg_id, title=title, notification=False, last_notification_time=None, reminder_message=None)
    

def get_all_projects_records():
    if Projects.select().exists():
        all_projects = Projects.select()
        projects_list = []
        for project in all_projects:
            project_dict = {
                'tg_id': project.tg_id,
                'title': project.title,
                'description': project.description,
                'comments': project.get_comments(),  
                'status': project.status,
                'deadline': project.deadline.strftime('%Y-%m-%d %H:%M:%S') if project.deadline else None
            }
            projects_list.append(project_dict)
        return projects_list
    else:
        return []
    

def update_statuses(statuses):
    with connection:
        for status in statuses:
            ProjectStatus.get_or_create(status_name=status)