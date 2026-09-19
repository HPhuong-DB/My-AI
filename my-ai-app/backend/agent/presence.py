"""Per-connection UI availability. Missing/stale presence always means silence."""
import time


class Presence:
    def __init__(self, now=time.monotonic):
        self.now = now
        self.sessions = {}

    def update(self, connection_id, user_id, payload):
        fields = ('visible', 'busy', 'typing', 'reading')
        if any(type(payload.get(key)) is not bool for key in fields):
            self.remove(connection_id)
            return False
        hour = payload.get('local_hour')
        if type(hour) is not int or not 0 <= hour <= 23:
            self.remove(connection_id)
            return False
        self.sessions[connection_id] = (user_id, self.now(), {key: payload[key] for key in (*fields, 'local_hour')})
        return True

    def remove(self, connection_id):
        self.sessions.pop(connection_id, None)

    def reason(self, user_id):
        live = [data for user, at, data in self.sessions.values() if user == user_id and self.now() - at < 45]
        visible = [data for data in live if data['visible']]
        if not visible:
            return 'not_present'
        # A busy visible tab blocks other tabs too, avoiding cross-tab interruptions.
        if any(data['busy'] or data['typing'] or data['reading'] for data in visible):
            return 'user_busy'
        if not any(8 <= data['local_hour'] < 22 for data in visible):
            return 'quiet_hours'
        return None
