/*
 * scv_music_seq.c -- tiny frame-based music sequencer helpers
 *
 * Include this source directly from demos:
 *   #include "../tools/scv_music_seq.c"
 *
 * Required globals in the including translation unit:
 *   int scv_music_playing;
 *   int scv_music_step_index;
 *   int scv_music_frame_tick;
 *   int scv_music_frames_per_step;
 */

int scv_music_playing;
int scv_music_step_index;
int scv_music_frame_tick;
int scv_music_frames_per_step;

void scv_music_seq_init(int frames_per_step) {
    scv_music_playing = 1;
    scv_music_step_index = 0;
    scv_music_frame_tick = 0;
    scv_music_frames_per_step = frames_per_step;
}

void scv_music_seq_set_tempo(int frames_per_step) {
    if (frames_per_step < 1) {
        frames_per_step = 1;
    }
    scv_music_frames_per_step = frames_per_step;
}

void scv_music_seq_toggle_play(void) {
    if (scv_music_playing == 1) {
        scv_music_playing = 0;
    } else {
        scv_music_playing = 1;
    }
}

/* Returns 1 when a new sequence step starts, otherwise 0. */
int scv_music_seq_tick(int sequence_length) {
    if (scv_music_playing == 0) {
        return 0;
    }

    scv_music_frame_tick = scv_music_frame_tick + 1;
    if (scv_music_frame_tick < scv_music_frames_per_step) {
        return 0;
    }

    scv_music_frame_tick = 0;
    scv_music_step_index = scv_music_step_index + 1;
    if (scv_music_step_index >= sequence_length) {
        scv_music_step_index = 0;
    }
    return 1;
}
