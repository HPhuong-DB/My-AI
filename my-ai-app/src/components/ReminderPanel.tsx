import type { useReminders } from '../hooks/useReminders';

export function ReminderPanel({ model }: { model: ReturnType<typeof useReminders> }) {
  if (!model.reminders.length && !model.error) return null;
  return <section className="reminder-panel" aria-labelledby="reminder-heading">
    <div className="reminder-panel__header"><strong id="reminder-heading">Nhắc nhở đang đến hạn</strong></div>
    {model.error && <p role="alert">{model.error} <button onClick={() => void model.refresh()}>Tải lại</button></p>}
    <ul className="reminder-list">{model.reminders.map((reminder) => <li key={reminder.id} className="reminder-item">
      <div className="reminder-item__content"><span className="reminder-item__title">{reminder.title}</span>{reminder.note && <small>{reminder.note}</small>}{reminder.scheduled_for && <small>{new Date(reminder.scheduled_for).toLocaleString()}</small>}</div>
      <button type="button" className="reminder-item__complete" onClick={() => void model.complete(reminder.id)}>Đánh dấu hoàn thành</button>
    </li>)}</ul>
  </section>;
}
