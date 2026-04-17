from __future__ import annotations

from easytour.utils.task_util import (
    add_done_task,
    add_running_task,
    get_done_task_list,
    get_running_task_list,
    get_task_status,
    update_task_status,
)


class TaskService:
    def mark_node_running(self, task_id: str, node_name: str) -> None:
        add_running_task(task_id, node_name)

    def mark_node_done(self, task_id: str, node_name: str) -> None:
        add_done_task(task_id, node_name)

    def update_task_status(self, task_id: str, status: str) -> None:
        update_task_status(task_id, status)

    def get_task_status(self, task_id: str) -> str:
        return get_task_status(task_id)

    def get_task_info(self, task_id: str) -> dict[str, object]:
        return {
            'status': get_task_status(task_id),
            'done_list': get_done_task_list(task_id),
            'running_list': get_running_task_list(task_id),
        }
