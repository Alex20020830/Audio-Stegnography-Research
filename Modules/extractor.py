from music21 import stream, note, chord, converter
from Modules.embedder import StegoEmbedder
import tempfile
import os

class StegoExtractor:
    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.embedder_helper = StegoEmbedder(analyzer)

    def _stabilize_score(self, score):
        fd, temp_path = tempfile.mkstemp(suffix='.mid')
        os.close(fd)
        try:
            score.write('midi', fp=temp_path)
            stabilized_score = converter.parse(temp_path)
            return stabilized_score
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def extract_message(self, original_score, stego_score):
        print("[Extractor] 啟動 V.3.5 同步提取模式 (Stable)...")
        
        orig_stable = self._stabilize_score(original_score)
        
        # 1. 建立 Stego 索引
        stego_list = []
        global_idx = 0
        for elem in stego_score.flat.getElementsByClass(['Note', 'Chord']):
            if isinstance(elem, note.Note):
                stego_list.append((global_idx, elem.offset, elem))
                global_idx += 1
            elif isinstance(elem, chord.Chord):
                for n in elem.notes:
                    stego_list.append((global_idx, elem.offset, n))
                    global_idx += 1
        
        stego_list.sort(key=lambda x: (x[1], x[2].pitch.ps))
        used_indices = set()

        orig_flat = orig_stable.flat
        window_size = self.analyzer.get_adaptive_window_size(orig_stable)
        max_offset = orig_stable.highestTime
        current_offset = 0.0
        
        extracted_bits = []
        TIME_TOLERANCE = 0.05
        
        while current_offset < max_offset:
            orig_window = orig_flat.getElementsByOffset(
                current_offset, current_offset + window_size, includeEndBoundary=False
            )
            
            target_data, _ = self.embedder_helper.select_targets_v3(
                orig_window, orig_flat, current_offset + window_size
            )
            
            if target_data:
                for original_note, target_abs_offset in target_data:
                    
                    if not self.embedder_helper.is_musically_safe(original_note, orig_window):
                        continue

                    candidates = []
                    for idx, s_time, s_note in stego_list:
                        if idx in used_indices: continue

                        time_diff = abs(s_time - target_abs_offset)
                        if s_time > target_abs_offset + TIME_TOLERANCE: break
                        if time_diff < TIME_TOLERANCE:
                            candidates.append((idx, s_note))
                    
                    best_match = None
                    best_match_idx = -1
                    min_pitch_diff = 999
                    
                    for idx, cand in candidates:
                        p_diff = abs(cand.pitch.ps - original_note.pitch.ps)
                        if p_diff < 3.0 and p_diff < min_pitch_diff:
                            min_pitch_diff = p_diff
                            best_match = cand
                            best_match_idx = idx

                    if best_match:
                        used_indices.add(best_match_idx)
                        vel = best_match.volume.velocity
                        if vel is None: vel = 64
                        
                        if vel % 2 == 0:
                            continue
                        else:
                            if min_pitch_diff > 0.5:
                                extracted_bits.append(1)
                            else:
                                extracted_bits.append(0)

            current_offset += window_size
            
        return extracted_bits