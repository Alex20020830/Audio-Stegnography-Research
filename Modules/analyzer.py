from music21 import converter, stream, note, chord, meter, key, scale, roman, pitch
import warnings

# 忽略 MIDI 解析時的非關鍵警告
warnings.filterwarnings("ignore")

class MusicAnalyzer:
    def __init__(self, default_window_size=1.0):
        self.default_window_size = default_window_size
        self.CONSTRAINT_THRESHOLD = 0.8 

    def get_adaptive_window_size(self, score):
        try:
            parts = score.getElementsByClass(stream.Part)
            if parts:
                measure = parts[0].getElementsByClass(stream.Measure)
                if measure:
                    ts = measure[0].getElementsByClass(meter.TimeSignature).first()
                else:
                    ts = score.flat.getElementsByClass(meter.TimeSignature).first()
            else:
                ts = score.flat.getElementsByClass(meter.TimeSignature).first()
        except:
            ts = None
        
        if ts is None:
            return self.default_window_size
        if ts.numerator % 3 == 0 and ts.denominator == 8:
            return 1.5 
        return 1.0

    def is_alberti_bass_pattern(self, notes):
        """
        [New] Alberti Bass 偵測器
        古典樂派常見伴奏：分解和弦 (Do-So-Mi-So)，通常位於低音部
        """
        if len(notes) < 3: return False
        
        # 1. 音域檢查：通常在低音區 (C4=60 以下)
        avg_pitch = sum(n.pitch.ps for n in notes) / len(notes)
        if avg_pitch > 65: return False # 放寬一點到 65
        
        # 2. 跨度檢查：Alberti Bass 通常在一個八度內
        pitches = sorted([n.pitch.ps for n in notes])
        span = pitches[-1] - pitches[0]
        if span > 14: return False # 超過大九度通常不是單純伴奏
        
        # 3. 形狀檢查：簡單判斷是否為分解和弦 (音高不完全相同)
        if len(set(pitches)) < 2: return False # 只有單音重複不算
        
        return True

    def analyze_constraint_level(self, notes, current_key):
        """分析約束等級 (加入 Alberti Bass 優化)"""
        if not notes: return "Type 3 (Low Constraint)"

        # [New Optimization] 優先檢查 Alberti Bass
        # 如果是伴奏音型，視為高安全性的 Standard Constraint (甚至可視為 Stable Triad)
        # 這能解鎖大量原本被視為 Type 3 的低音伴奏
        if self.is_alberti_bass_pattern(notes):
            return "Type 2 (Standard Constraint)"

        note_pcs = [n.pitch.pitchClass for n in notes]
        total_notes = len(note_pcs)
        if total_notes == 0: return "Type 3 (Low Constraint)"

        tonic_pc = current_key.tonic.pitchClass
        if current_key.mode == 'major': p_scale_offsets = [0, 2, 4, 7, 9]
        else: p_scale_offsets = [0, 3, 5, 7, 10]
        p_scale_pcs = set([(tonic_pc + o) % 12 for o in p_scale_offsets])
        
        match_count = sum(1 for pc in note_pcs if pc in p_scale_pcs)
        if (match_count / total_notes) >= self.CONSTRAINT_THRESHOLD:
            return "Type 1 (High Constraint)"

        try:
            d_scale_pcs = set([p.pitchClass for p in current_key.pitches])
        except:
            d_offsets = [0, 2, 4, 5, 7, 9, 11]
            d_scale_pcs = set([(tonic_pc + o) % 12 for o in d_offsets])
        
        match_count_diatonic = sum(1 for pc in note_pcs if pc in d_scale_pcs)
        if (match_count_diatonic / total_notes) >= self.CONSTRAINT_THRESHOLD:
            return "Type 2 (Standard Constraint)"

        return "Type 3 (Low Constraint)"

    def identify_harmony(self, window_stream, current_key):
        """和聲識別 (加入 Alberti Bass 優化)"""
        all_pitches = set()
        notes_in_window = []
        for elem in window_stream:
            if isinstance(elem, chord.Chord):
                for p in elem.pitches: all_pitches.add(p.name)
                notes_in_window.extend(elem.notes)
            elif isinstance(elem, note.Note):
                all_pitches.add(elem.pitch.name)
                notes_in_window.append(elem)
        
        if not all_pitches: return "Ambiguous"

        # [New] Alberti Bass 視為穩定三和弦
        if self.is_alberti_bass_pattern(notes_in_window):
            return "Stable Triad"

        c = chord.Chord(list(all_pitches))
        try:
            rn = roman.romanNumeralFromChord(c, current_key)
            if rn.isTriad(): return "Stable Triad"
            if rn.isSeventh(): return "Dominant 7th" if rn.domogs else "Other 7th"
        except: pass 

        if c.isDominantSeventh(): return "Dominant 7th"
        if c.root() and c.third:
            if c.isConsonant() or c.isTriad(): return "Stable Triad"

        return "Ambiguous"