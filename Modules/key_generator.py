import os
from Modules.cryptographer import MedicalEncryptor

def generate_doctor_keys():
    print("="*50)
    print("   [醫生端] 金鑰生成工具 (Run Once)")
    print("="*50)

    # 設定存放路徑
    keys_dir = "Keys"
    os.makedirs(keys_dir, exist_ok=True)

    encryptor = MedicalEncryptor()
    
    # 1. 生成 ECC 金鑰對
    print("正在生成 NIST P-256 (secp256r1) 金鑰對...")
    private_key, public_key = encryptor.generate_ecc_keys()

    # 2. 儲存私鑰 (doctor_private.pem) -> 醫生自己留著，絕對不外流
    priv_path = os.path.join(keys_dir, "doctor_private.pem")
    with open(priv_path, "wt") as f:
        f.write(private_key.export_key(format='PEM'))
    print(f"私鑰已儲存: {priv_path} (請妥善保管!)")

    # 3. 儲存公鑰 (doctor_public.pem) -> 這把要給病人(傳送者)
    pub_path = os.path.join(keys_dir, "doctor_public.pem")
    with open(pub_path, "wt") as f:
        f.write(public_key.export_key(format='PEM'))
    print(f"公鑰已儲存: {pub_path} (請發布給病人)")

if __name__ == "__main__":
    generate_doctor_keys()