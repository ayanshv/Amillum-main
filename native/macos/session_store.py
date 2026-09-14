"""Small credentials in macOS Keychain only; never plaintext files or shell args."""
import json
import Security as S
from Foundation import NSData


class SessionStore:
    def __init__(self, service='com.amillum.session'):
        self.service = service

    def query(self, name):
        return {S.kSecClass: S.kSecClassGenericPassword, S.kSecAttrService: self.service,
                S.kSecAttrAccount: name, S.kSecUseDataProtectionKeychain: True}

    def read(self, name):
        query = self.query(name)
        query.update({S.kSecReturnData: True, S.kSecMatchLimit: S.kSecMatchLimitOne})
        status, data = S.SecItemCopyMatching(query, None)
        if status == S.errSecItemNotFound:
            return None
        if status != 0:
            raise RuntimeError('Keychain is unavailable. Unlock your Mac and retry.')
        return json.loads(bytes(data).decode())

    def write(self, name, value):
        raw = json.dumps(value).encode()
        data = NSData.dataWithBytes_length_(raw, len(raw))
        query = self.query(name)
        status = S.SecItemUpdate(query, {S.kSecValueData: data})
        if status == S.errSecItemNotFound:
            query.update({S.kSecValueData: data, S.kSecAttrAccessible: S.kSecAttrAccessibleWhenUnlockedThisDeviceOnly})
            status, _ = S.SecItemAdd(query, None)
        if status != 0:
            raise RuntimeError('Your session could not be saved in Keychain. Unlock your Mac and retry.')

    def delete(self, name):
        status = S.SecItemDelete(self.query(name))
        if status not in (0, S.errSecItemNotFound):
            raise RuntimeError('Keychain could not clear the saved session. Unlock your Mac and retry logout.')
