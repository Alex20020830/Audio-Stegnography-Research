import matplotlib.pyplot as plt
import numpy as np
from music21 import converter, note, chord
import os
import glob

# ================= 配置區塊 =================
BASE_DIR = r"C:/Users/user/Desktop/PythonWorkspace/AudioSteganography"

# 精準設定你的 3 個案例路徑
CASES = [
    {
        "title": "Best Case (Beethoven Op.57 Appassionata)\nKLD = 0.002",
        "orig_path": os.path.join(BASE_DIR, r"Experience/Experience MIDI/Beethoven Piano Sonata No.23 Op.57 Appassionata"),
        "stego_path": os.path.join(BASE_DIR, r"Generated Files/Stego Result/Beethoven Piano Sonata No.23 Op.57 Appassionata/Beethoven Piano Sonata No.23 Op.57 Appassionata_Complete_Stego.mid")
    },
    {
        "title": "Large Scale Case (Mozart K.448)\nKLD = 0.001",
        "orig_path": os.path.join(BASE_DIR, r"Experience/Experience MIDI/Mozart Piano Sonata for Two Pianos in D major, K.448"),
        "stego_path": os.path.join(BASE_DIR, r"Generated Files/Stego Result/Mozart Piano Sonata for Two Pianos in D major, K.448/Mozart Piano Sonata for Two Pianos in D major, K.448_Complete_Stego.mid")
    },
    {
        "title": "Worst Case (Haydn Hob.XVI 40)\nKLD = 0.021",
        "orig_path": os.path.join(BASE_DIR, r"Experience/Experience MIDI/Haydn Piano Sonata Hob.XVI 40 in G major"),
        "stego_path": os.path.join(BASE_DIR, r"Generated Files/Stego Result/Haydn Piano Sonata Hob.XVI 40 in G major/Haydn Piano Sonata Hob.XVI 40 in G major_Complete_Stego.mid")
    }
]
# ============================================

def get_pitch_frequencies(target_path):
    """
    智慧讀取函數：
    - 如果傳入的是「資料夾」，會自動合併裡面所有的 .mid (適用於 Original 多樂章)
    - 如果傳入的是「特定檔案」，就只讀該檔案 (適用於 Stego_Complete)
    """
    pitch_counts = {}
    files_to_process = []
    
    if os.path.isfile(target_path) and target_path.endswith('.mid'):
        files_to_process.append(target_path)
    elif os.path.isdir(target_path):
        files_to_process = glob.glob(os.path.join(target_path, "*.mid"))
    else:
        print(f"❌ 找不到路徑或檔案: {target_path}")
        return {}

    if not files_to_process:
        print(f"⚠️ 在 {target_path} 中找不到任何 .mid 檔案！")
        return {}

    for midi_path in files_to_process:
        filename = os.path.basename(midi_path)
        print(f"   讀取: {filename}")
        try:
            score = converter.parse(midi_path)
            for elem in score.flat.notes:
                pitches_to_add = []
                if isinstance(elem, note.Note):
                    pitches_to_add.append(elem.pitch.ps)
                elif isinstance(elem, chord.Chord):
                    pitches_to_add.extend([p.ps for p in elem.pitches])
                    
                for p in pitches_to_add:
                    pitch_counts[p] = pitch_counts.get(p, 0) + 1
        except Exception as e:
            print(f"   讀取 {filename} 失敗: {e}")

    return pitch_counts

def plot_academic_histograms():
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('Pitch Histogram Comparison (Resistance against Statistical Attacks)', fontsize=16, fontweight='bold', y=1.05)

    for i, case in enumerate(CASES):
        print(f"\n[{i+1}/3] 正在處理: {case['title'].splitlines()[0]}")
        ax = axes[i]
        
        print(" -> 分析 Original...")
        orig_counts = get_pitch_frequencies(case["orig_path"])
        
        print(" -> 分析 Stego...")
        stego_counts = get_pitch_frequencies(case["stego_path"])
        
        if not orig_counts or not stego_counts:
            ax.set_title(f"{case['title']}\n(Data Missing)", color='red')
            continue
            
        all_pitches = set(orig_counts.keys()).union(set(stego_counts.keys()))
        min_pitch, max_pitch = int(min(all_pitches)) - 2, int(max(all_pitches)) + 2
        x_axis = np.arange(min_pitch, max_pitch + 1)
        
        y_orig = [orig_counts.get(x, 0) for x in x_axis]
        y_stego = [stego_counts.get(x, 0) for x in x_axis]
        
        # 繪製重疊直方圖
        ax.bar(x_axis, y_orig, width=0.8, alpha=0.6, color='royalblue', label='Original')
        ax.bar(x_axis, y_stego, width=0.8, alpha=0.6, color='darkorange', label='Stego')
        
        ax.set_title(case["title"], fontsize=14)
        ax.set_xlabel('MIDI Pitch Number', fontsize=12)
        if i == 0:
            ax.set_ylabel('Note Count (Frequency)', fontsize=12)
            
        ax.legend(fontsize=10)
        ax.grid(axis='y', linestyle='--', alpha=0.7)

    plt.tight_layout()
    output_filename = os.path.join(BASE_DIR, "Academic_Histogram_Proof.png")
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    print(f"\n✅ 繪圖完成！已儲存為: {output_filename}")

if __name__ == "__main__":
    plot_academic_histograms()