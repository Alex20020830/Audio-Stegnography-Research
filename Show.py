import pretty_midi

# 載入 MIDI
pm = pretty_midi.PrettyMIDI('Generated Files/Stego Result/20260119_201853/Stego_Piano Sonata No.16 Movement 1_20260119_201853.mid')

# 查看所有樂器
print(f"Total length: {pm.get_end_time()} second")

for instrument in pm.instruments:
    print(f"\n Instrument type: {instrument.name}, Instrument No.: {instrument.program}")
    
    # 列出前 5 個音符的詳細數值
    for note in instrument.notes[:5]:
        print(f"Pitch: {note.pitch}, Velocity: {note.velocity}, "
              f"Start time: {note.start}s, End time: {note.end}s")