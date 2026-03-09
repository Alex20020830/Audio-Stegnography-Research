from Crypto.Cipher import AES
from Crypto.PublicKey import ECC
from Crypto.Protocol.KDF import HKDF
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
import binascii

class MedicalEncryptor:
    def __init__(self):
        self.aes_key_size = 32  # AES-256
        self.curve = 'P-256'    # NIST P-256 (secp256r1)

    def get_random_bytes(self, size):
        return get_random_bytes(size)

    # --- 1. ECC 金鑰管理 ---
    def generate_ecc_keys(self):
        key = ECC.generate(curve=self.curve)
        return key, key.public_key()

    # --- 2. ECIES 加密 ---
    def encrypt_aes_key_with_ecc(self, aes_key, recipient_public_key):
        """
        實作 ECIES 加密 (壓縮版)
        回傳長度固定為 97 bytes (33 Pub + 16 Nonce + 16 Tag + 32 Key)
        """
        ephemeral_key = ECC.generate(curve=self.curve)
        shared_point = ephemeral_key.d * recipient_public_key.pointQ
        shared_secret = int(shared_point.x).to_bytes(32, 'big')
        derived_key = HKDF(shared_secret, 32, b'', SHA256)
        
        cipher = AES.new(derived_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(aes_key)
        
        # [壓縮開啟] compress=True -> 公鑰長度變為 33 bytes
        pub_bytes = ephemeral_key.public_key().export_key(format='SEC1', compress=True)
        
        return pub_bytes + cipher.nonce + tag + ciphertext

    def decrypt_aes_key_with_ecc(self, encrypted_packet, recipient_private_key):
        """
        實作 ECIES 解密 (壓縮版適配)
        """
        try:
            # [關鍵修改] 適應壓縮格式的切分點
            # Compressed PubKey = 33 bytes (原為 65)
            pub_bytes = encrypted_packet[:33]      # 0~33
            nonce = encrypted_packet[33:49]        # 33~49 (16 bytes)
            tag = encrypted_packet[49:65]          # 49~65 (16 bytes)
            ciphertext = encrypted_packet[65:]     # 65~97 (32 bytes)
            
            ephemeral_public_key = ECC.import_key(pub_bytes, curve_name=self.curve)
            shared_point = recipient_private_key.d * ephemeral_public_key.pointQ
            shared_secret = int(shared_point.x).to_bytes(32, 'big')
            derived_key = HKDF(shared_secret, 32, b'', SHA256)
            
            cipher = AES.new(derived_key, AES.MODE_GCM, nonce=nonce)
            aes_key = cipher.decrypt_and_verify(ciphertext, tag)
            return aes_key
        except Exception as e:
            print(f"[Crypto] 解密失敗: {e}")
            return None

    # --- 3. AES-256 加密醫療影像 ---
    def encrypt_image_aes(self, image_data, aes_key):
        cipher = AES.new(aes_key, AES.MODE_EAX)
        ciphertext, tag = cipher.encrypt_and_digest(image_data)
        return cipher.nonce, tag, ciphertext

    def decrypt_image_aes(self, nonce, tag, ciphertext, aes_key):
        try:
            cipher = AES.new(aes_key, AES.MODE_EAX, nonce=nonce)
            data = cipher.decrypt_and_verify(ciphertext, tag)
            return data
        except ValueError:
            print("[Crypto] AES 驗證失敗")
            return None

    # --- 4. Payload 建構與解析 ---
    def construct_payload(self, file_id, encrypted_aes_key_packet):
        id_bytes = file_id.encode('utf-8')
        separator = b':::'
        full_payload_bytes = id_bytes + separator + encrypted_aes_key_packet
        
        result = []
        for byte in full_payload_bytes:
            bits = bin(byte)[2:].zfill(8)
            result.extend([int(b) for b in bits])
        return result

    def unpack_payload(self, bits):
        """
        將 Bit Stream 還原 (壓縮版適配)
        """
        byte_array = bytearray()
        for i in range(0, len(bits), 8):
            byte_chunk = bits[i:i+8]
            if len(byte_chunk) < 8: break
            byte_str = ''.join(str(b) for b in byte_chunk)
            byte_val = int(byte_str, 2)
            byte_array.append(byte_val)
            
        full_data = bytes(byte_array)
        
        separator = b':::'
        if separator not in full_data:
            return None, None
            
        try:
            id_bytes, encrypted_packet = full_data.split(separator, 1)
            
            # [關鍵修改] 壓縮封包總長度為 97 bytes
            # (33 Pub + 16 Nonce + 16 Tag + 32 Key)
            encrypted_packet = encrypted_packet[:97]
            
            return id_bytes.decode('utf-8'), encrypted_packet
        except:
            return None, None

    def string_to_bits(self, s):
        result = []
        for char in s:
            bits = bin(ord(char))[2:].zfill(8)
            result.extend([int(b) for b in bits])
        return result