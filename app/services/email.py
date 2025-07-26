from fastapi import BackgroundTasks
from app.utils.email_renderer import render_email_template
from app.utils.email_sender import send_email_async



class EmailService:
    def __init__(self):
        pass

    def schedule_shipment_email(self, to_email: str, cc_email, subject: str, context: dict, template_name: str, background_tasks: BackgroundTasks):
        html_body = render_email_template(template_name, context)

        background_tasks.add_task(
            send_email_async,
            to_email,
            cc_email,
            subject,
            html_body,
            "html"
        )
