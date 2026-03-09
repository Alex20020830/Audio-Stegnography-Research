from music21 import stream, note, chord, interval, pitch, scale, converter
import copy
import tempfile
import os

class StegoEmbedder:
    def __init__(self, analyzer):
        self.analyzer = analyzer

    def _stabilize_score(self, score):
        """[V.3.3] 樂譜穩定化"""
        fd, temp_path = tempfile.mkstemp(suffix='.mid')
        os.close(fd)
        try:
            score.write('midi', fp=temp_path)
            stabilized_score = converter.parse(temp_path)
            return stabilized_score
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def calculate_capacity(self, score):
        """
        [Stats] 真實容量預估 (Stable Version)
        """
        print("   [Capacity] 正在計算此樂章的『真實』嵌入空間...")
        temp_score = self._stabilize_score(copy.deepcopy(score))
        
        window_size = self.analyzer.get_adaptive_window_size(temp_score)
        flat_stream = temp_score.flat
        max_offset = temp_score.highestTime
        current_offset = 0.0
        capacity = 0
        
        while current_offset < max_offset:
            window_elements = flat_stream.getElementsByOffset(
                current_offset, current_offset + window_size, includeEndBoundary=False
            )
            
            target_data, next_ref = self.select_targets_v3(
                window_elements, flat_stream, current_offset + window_size
            )
            
            try:
                current_key = flat_stream.getElementsByOffset(0, current_offset).getElementsByClass('KeySignature').last()
                if not current_key: current_key = temp_score.analyze('key')
                if not hasattr(current_key, 'tonic'): current_key = current_key.asKey()
                raw_notes = [x[0] for x in target_data]
                constraint_type = self.analyzer.analyze_constraint_level(raw_notes, current_key)
            except:
                constraint_type = "Type 2 (Standard Constraint)"
                current_key = None

            for target_note, _ in target_data:
                if self.is_musically_safe(target_note, window_elements):
                    test_note = copy.deepcopy(target_note)
                    if self.apply_bounded_smart_modification(test_note, constraint_type, current_key, next_ref):
                        capacity += 1
            
            current_offset += window_size
            
        print(f"   [Capacity] 結果: 可嵌入 {capacity} bits")
        return capacity

    def embed_message(self, score, secret_bits):
        print(f"[Embedder] 啟動 V.3.4 (Stable: Threshold 0.18)...")
        
        stego_score = self._stabilize_score(score)
        
        # Step A: Velocity Reset
        for n in stego_score.flat.notes:
            if n.volume.velocity is None: n.volume.velocity = 64
            if n.volume.velocity % 2 != 0: n.volume.velocity -= 1
            
            if isinstance(n, chord.Chord):
                for inner in n.notes:
                    if inner.volume.velocity is None: inner.volume.velocity = 64
                    if inner.volume.velocity % 2 != 0: inner.volume.velocity -= 1
        
        # Step B: Embedding
        window_size = self.analyzer.get_adaptive_window_size(stego_score)
        flat_stream = stego_score.flat
        max_offset = stego_score.highestTime
        current_offset = 0.0
        bit_index = 0
        
        while current_offset < max_offset:
            if bit_index >= len(secret_bits): break 

            window_elements = flat_stream.getElementsByOffset(
                current_offset, current_offset + window_size, includeEndBoundary=False
            )
            
            target_data, next_ref = self.select_targets_v3(
                window_elements, flat_stream, current_offset + window_size
            )
            
            try:
                current_key = flat_stream.getElementsByOffset(0, current_offset).getElementsByClass('KeySignature').last()
                if not current_key: current_key = stego_score.analyze('key')
                if not hasattr(current_key, 'tonic'): current_key = current_key.asKey()
                
                raw_notes = [x[0] for x in target_data]
                constraint_type = self.analyzer.analyze_constraint_level(raw_notes, current_key)
            except:
                constraint_type = "Type 2 (Standard Constraint)"
                current_key = None

            for target_note, _ in target_data:
                if bit_index >= len(secret_bits): break 

                if not self.is_musically_safe(target_note, window_elements):
                    continue

                secret_bit = secret_bits[bit_index]
                is_embedded = False 
                
                if secret_bit == 0:
                    is_embedded = True
                elif secret_bit == 1:
                    success = self.apply_bounded_smart_modification(
                        target_note, constraint_type, current_key, next_ref
                    )
                    if success:
                        is_embedded = True
                    else:
                        is_embedded = False
                
                if is_embedded:
                    target_note.volume.velocity += 1
                    bit_index += 1
                
            current_offset += window_size

        return stego_score, bit_index

    def is_musically_safe(self, target_note, window_elements):
        simultaneous_notes = []
        for elem in window_elements:
            if isinstance(elem, note.Note):
                if abs(elem.offset - target_note.offset) < 0.05:
                    simultaneous_notes.append(elem)
            elif isinstance(elem, chord.Chord):
                if abs(elem.offset - target_note.offset) < 0.05:
                    simultaneous_notes.extend(elem.notes)
        
        if not simultaneous_notes: return False
        
        if target_note.offset % 1.0 < 0.01 or target_note.offset % 1.0 > 0.99: return False
        
        if target_note.pitch.ps < 48: return False
        
        highest_note = max(simultaneous_notes, key=lambda n: n.pitch.ps)
        is_polyphonic = (len(simultaneous_notes) >= 2)
        if is_polyphonic:
            if target_note is highest_note: return False
            return True
        else:
            return True

    def select_targets_v3(self, window_elements, flat_stream, next_offset):
        all_notes_data = []
        for elem in window_elements:
            if isinstance(elem, chord.Chord):
                for n in elem.notes: all_notes_data.append( (n, elem.offset) )
            elif isinstance(elem, note.Note):
                all_notes_data.append( (elem, elem.offset) )
        
        if not all_notes_data: return [], None

        all_notes_data.sort(key=lambda x: (x[1], x[0].pitch.ps))
        
        # [Revert] 回到最穩定的 0.18 (配合 round)
        valid_data = [x for x in all_notes_data if round(x[0].duration.quarterLength, 2) >= 0.18]
        
        SAFETY_RADIUS = 1.1 
        safe_candidates = []
        
        for i, (n1, off1) in enumerate(valid_data):
            is_physically_safe = True
            p1 = n1.pitch.ps
            for j, (n2, off2) in enumerate(valid_data):
                if i == j: continue
                if abs(off1 - off2) < 0.05:
                    if abs(p1 - n2.pitch.ps) <= SAFETY_RADIUS:
                        is_physically_safe = False; break
            if is_physically_safe: safe_candidates.append((n1, off1))

        next_ref = None
        try:
            next_elems = flat_stream.getElementsByOffset(next_offset, next_offset + 1.0)
            for e in next_elems:
                if isinstance(e, note.Note): next_ref = e; break
                elif isinstance(e, chord.Chord): next_ref = e.notes[0]; break
        except: pass
        
        return safe_candidates, next_ref

    def apply_bounded_smart_modification(self, target_note, constraint_type, current_key, next_ref_note):
        direction = 'ascending'
        try:
            if next_ref_note:
                ref_ps = next_ref_note.pitch.ps if hasattr(next_ref_note, 'pitch') else next_ref_note.root().ps
                if ref_ps > target_note.pitch.ps: direction = 'ascending'
                else: direction = 'descending'
        except: pass

        original_ps = target_note.pitch.ps

        if constraint_type == "Type 1 (High Constraint)" and current_key:
            try:
                tonic = current_key.tonic
                if current_key.mode == 'major': intervals = ['P1', 'M2', 'M3', 'P5', 'M6']
                else: intervals = ['P1', 'm3', 'P4', 'P5', 'm7']
                pitches = [tonic.transpose(i) for i in intervals]
                sc = scale.ConcreteScale(pitches=pitches)
                new_pitch = sc.next(target_note.pitch, direction=direction)
                if abs(new_pitch.ps - original_ps) <= 2.0:
                    target_note.pitch = new_pitch
                    return True
            except: pass 

        try:
            semitone = 1 if direction == 'ascending' else -1
            target_note.transpose(semitone, inPlace=True)
            return True
        except: return False