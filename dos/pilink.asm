; PILINK.COM: the Raspberry Pi's direct line to the Compaq's screen and keys.
;
; MS-DOS Kermit is a terminal: the Pi can only send it what a VT102 or a
; Tektronix understands, at the speed Kermit's own drawing code keeps up
; with. PILINK takes Kermit out of the way. It reads the serial port itself
; (up to 115200 baud), puts what arrives straight into video memory, and
; sends every key press AND release back, which no terminal can. The Pi
; keeps a copy of the screen and sends only what changed: pictures, and
; when PILINK is the Compaq's terminal (PI.BAT), the text too.
;
;   PILINK [divisor] [/K] [/N] [/2]
;     divisor  the speed to start at, as 115200 divided by it (12 = 9600,
;              3 = 38400, 1 = 115200). Left out: 9600, or with /K whatever
;              Kermit left the port at.
;     /K       started by Kermit (the Pi asks it to RUN PILINK): keep the
;              port's speed, and go back to Kermit when the Pi goes quiet.
;              Without it PILINK is the Compaq's terminal: when the Pi goes
;              quiet it waits for it to come back.
;     /N       don't use the serial chip's buffer (FIFO), even if it has one
;     /2       COM2 instead of COM1
;   Ctrl+Alt+Esc (or Ctrl+Alt+Del) leaves, whatever the Pi is doing.
;   Exit codes (ERRORLEVEL, for PI.BAT): 0 the Pi said quit, 1 Ctrl+Alt+Esc,
;   2 the Pi went quiet (with /K), or the code the Pi gave (D2).
;
; What the Pi sends (one opcode byte, then its arguments; words low byte
; first). "Here" is a position in video memory (segment B800), kept from one
; command to the next:
;   00-3F          skip (opcode + 1) bytes
;   40-7F          the next (opcode - 3F) bytes go on the screen here
;   80-BF  v       (opcode - 7F) copies of v go on the screen here
;   C0             nothing (the Pi's "still here")
;   C1  addr       here = addr
;   C2  n, bytes   like 40-7F, for n bytes
;   C3  n v        like 80-BF, n copies
;   C4  back n     copy n bytes from "back" bytes before here, to here
;   C5  src dst n  copy n bytes from src to dst (they may overlap)
;   C6  s          scale: low 4 bits 1, 2 or 4 (each byte sent becomes that
;                  many, every dot widened), high 4 bits 1 or 2 (2: each
;                  write is repeated 2000h further on, which on the CGA is
;                  the next row down)
;   C7  n, bytes   n bytes, each one more than the last, checked and thrown
;                  away (a test of the line at a new speed)
;   C8  m          BIOS video mode m. Answers 'M' and the mode now set.
;   C9  row col    text cursor
;   CA  port v     write v to an I/O port
;   CB  port       read an I/O port. Answers 'I' and the value.
;   CC  ax bx cx dx  INT 10h. Answers 'V' AL and 'v' AH.
;   CD  n          PC speaker: timer divisor n (0: quiet)
;   CE  divisor    change speed. Answers 'B' at the old speed, then switches.
;                  If nothing valid arrives for 1.5 s it goes back.
;   CF  n          end of a frame. Answers 'A' n.
;   D0             who's there? Answers the hello (below).
;   D1             quit: answers 'Q' 0, puts everything back, returns to DOS
;   D2  code       the same, with that exit code (10: PI.BAT runs Kermit for
;                  a file transfer, then PILINK again)
;   D3  a n, chars text: n characters (1-255) go on the screen here, each
;                  with attribute a (half the bytes of 40-7F for text)
;   D4  n, bytes   run something on DOS: the n bytes (up to 1024) become
;                  C:\PI\PIRUN.BAT, then it answers 'Q' 0 and leaves with
;                  exit code 12, and PI.BAT runs PIRUN, which ends by
;                  starting PI again. If the file can't be written it
;                  answers 'E' 1 and stays.
;   D5  n, name    is there a file called that (a DOS name, up to 127
;                  characters, wildcards allowed)? Answers 'F' 1 or 'F' 0.
;
; What PILINK sends, two bytes at a time, a letter and a value:
;   'K' scancode   a key went down (01-58) or up (81-D8), as the keyboard
;                  says it, E0 prefixes and all
;   'A' n          frame n is on the screen
;   'N' why        bytes were lost (serial chip error bits, 01 a command
;                  stopped halfway, 20 not a command, 40 test bytes wrong,
;                  80 our buffer overflowed). PILINK throws away what
;                  arrives until the line has been quiet a third of a second,
;                  then says 'R' 0: the Pi sends the whole screen again.
;   'M', 'I', 'V', 'v', 'B', 'Q', 'E', 'F': answers, as above ('Q' 1:
;                  Ctrl+Alt+Esc, 'Q' 2: the Pi went quiet)
; Until the Pi has spoken, only a command (C0 or above) starts the
; conversation: anything else is ignored, so text the Pi meant for Kermit
; (seven-bit, always) can't be taken for commands.
; And the hello, when it starts, when asked, and every 2 seconds until the
; Pi speaks: ESC _ P L version flags mode ESC \ , the three values each with
; 20h added. Flags: 1 the serial chip's buffer is in use, 2 started by
; Kermit. (Version 2 added D2 and D3; version 3 D4 and D5, and a loss
; spoils only the frame on its way: see lostcheck.) (No key on a terminal sends ESC _, so the Pi can tell a hello
; from typing.)
;
; Build: nasm -f bin -o PILINK.COM pilink.asm   (tools/build-pilink.sh)

        cpu     286
        org     100h

VERSION         equ 3
RSIZE           equ 4096        ; bytes of receive buffer (a power of two)
KSIZE           equ 32          ; keys waiting to be sent
TSIZE           equ 64          ; bytes waiting to be sent
STARVE_TICKS    equ 9           ; half a second (a tick is 1/18.2 s)
QUIET_TICKS     equ 6           ; a third of a second
TRIAL_TICKS     equ 27          ; 1.5 seconds
HELLO_TICKS     equ 36          ; 2 seconds
SILENCE_TICKS   equ 273         ; 15 seconds
NUM_EXT         equ 16h         ; opcodes C0 to D5
RUNMAX          equ 1024        ; bytes of a PIRUN.BAT
RUN_EXIT        equ 12          ; the exit code that has PI.BAT run it

; jmpif CONDITION, LABEL: a conditional jump of any length (the 286's own
; reach 127 bytes).
%macro  jmpif 2
        j%-1    %%no
        jmp     %2
%%no:
%endmacro

; lostcheck: stop at once if bytes were lost. Used after a command's count
; or addresses and before it writes: the serial interrupt marks a loss
; before it keeps the next byte, so a command never acts on a count that
; came after one, and a loss spoils only what the frame meant to change
; (the Pi then sends just that again, not the whole screen).
%macro  lostcheck 0
        test    byte [rxerr],0FFh
        jmpif   nz, line_error
%endmacro

start:
        cld
        mov     [base_sp],sp
        call    arguments
        call    make_tables
        call    find_port
        call    take_over
        call    banner
        call    hello
        xor     di,di

; ------------------------------------------------------------ the main loop

dispatch:
        mov     byte [incmd],0
        test    byte [rxerr],0FFh
        jmpif   nz, line_error
        mov     ax,[khead]              ; anything to send? (keys, answers)
        cmp     ax,[ktail]
        jne     .pump
        mov     ax,[thead]
        cmp     ax,[ttail]
        je      .read
.pump:  call    txpump
        cmp     byte [quit],0
        jmpif   ne, local_quit
.read:  call    getc
        cmp     byte [linked],0
        jne     .linked
        cmp     al,0C0h                 ; until the Pi has spoken, only a command
        jb      dispatch                ; (C0 or above) counts: text for Kermit is ignored
.linked:
        mov     byte [incmd],1
        mov     byte [linked],1
        cmp     al,0C0h
        jmpif   ae, extended
        mov     cl,al
        and     cx,003Fh
        inc     cx                      ; 1 to 64
        cmp     al,80h
        jmpif   ae, do_fill
        cmp     al,40h
        jmpif   ae, do_lit
do_skip:
        mov     ax,cx
        mov     cl,[hshift]
        shl     ax,cl
        add     di,ax
        jmp     dispatch

; CX bytes from the Pi go on the screen.
do_lit: cmp     word [emit],emit_11
        jne     .slow
.next:  mov     bx,[rtail]              ; as many as have arrived, in one move
        mov     ax,[rhead]
        cmp     ax,bx
        jne     .have
        call    idle
        jmp     .next
.have:  ja      .run
        mov     ax,RSIZE                ; (the buffer wraps: up to its end)
.run:   sub     ax,bx
        cmp     ax,cx
        jbe     .move
        mov     ax,cx
.move:  sub     cx,ax
        mov     dx,cx
        mov     cx,ax
        lea     si,[rbuf+bx]
        add     bx,ax
        and     bx,RSIZE-1
        rep     movsb
        mov     [rtail],bx
        mov     byte [idling],0
        mov     cx,dx
        or      cx,cx
        jnz     .next
        jmp     dispatch
.slow:  call    getc
        call    [emit]
        loop    .slow
        jmp     dispatch

; CX copies of the next byte go on the screen.
do_fill:
        call    getc
        lostcheck
        cmp     word [emit],emit_11
        jne     .slow
        rep     stosb
        jmp     dispatch
.slow:  mov     dl,al
.each:  mov     al,dl
        call    [emit]
        loop    .each
        jmp     dispatch

extended:
        sub     al,0C0h
        cmp     al,NUM_EXT
        jmpif   ae, bad_op
        xor     ah,ah
        mov     bx,ax
        shl     bx,1
        jmp     [ext_table+bx]

x_nop:  jmp     dispatch

x_seek: call    getw
        mov     di,ax
        jmp     dispatch

x_litw: call    getw
        lostcheck
        mov     cx,ax
        jcxz    x_nop
        jmp     do_lit
x_fillw:
        call    getw
        mov     cx,ax
        jcxz    .none
        jmp     do_fill
.none:  call    getc                    ; (its value, unused)
        jmp     dispatch

x_back: call    getw
        push    ax
        call    getw
        lostcheck
        mov     cx,ax
        pop     dx
        mov     si,di
        sub     si,dx
        push    ds
        push    es
        pop     ds
        rep     movsb                   ; (forwards, so a short "back" repeats a pattern)
        pop     ds
        jmp     dispatch

x_copy: call    getw
        push    ax
        call    getw
        push    ax
        call    getw
        lostcheck
        mov     cx,ax
        pop     di
        pop     si
        mov     dx,di
        add     dx,cx                   ; here, afterwards
        push    ds
        push    es
        pop     ds
        cmp     di,si
        jbe     .move
        add     si,cx                   ; moving up: from the end, backwards
        add     di,cx
        dec     si
        dec     di
        std
.move:  rep     movsb
        cld
        pop     ds
        mov     di,dx
        jmp     dispatch

x_scale:
        call    getc
        mov     ah,al
        and     al,0Fh
        shr     ah,4
        xor     bx,bx                   ; BX: which emitter (2 bytes each)
        cmp     al,1
        je      .rows
        mov     bl,4
        cmp     al,2
        je      .rows
        mov     bl,8
        cmp     al,4
        jmpif   ne, bad_op
.rows:  cmp     ah,1
        je      .set
        add     bl,2
        cmp     ah,2
        jmpif   ne, bad_op
.set:   mov     dx,[emitters+bx]
        mov     [emit],dx
        shr     al,1                    ; 1, 2, 4 -> a shift of 0, 1, 2
        mov     [hshift],al
        jmp     dispatch

x_sink: call    getw
        mov     cx,ax
        jcxz    .done
        xor     dh,dh                   ; DH: nonzero once a byte is wrong
        call    getc
        mov     dl,al
        dec     cx
        jz      .check
.each:  call    getc
        inc     dl
        cmp     al,dl
        je      .ok
        mov     dh,1
.ok:    loop    .each
.check: or      dh,dh
        jz      .done
        mov     byte [rxerr],40h
.done:  jmp     dispatch

x_mode: call    getc
        push    di
        xor     ah,ah
        int     10h
        mov     byte [mode_set],1
        call    video_mode
        pop     di
        mov     ah,al
        mov     al,'M'
        call    send2
        xor     di,di
        mov     word [emit],emit_11
        mov     byte [hshift],0
        call    video_segment
        jmp     dispatch

x_cursor:
        call    getc
        mov     dh,al
        call    getc
        mov     dl,al
        push    di
        mov     ah,2
        xor     bh,bh
        int     10h
        pop     di
        call    video_segment
        jmp     dispatch

x_out:  call    getw
        mov     dx,ax
        call    getc
        out     dx,al
        jmp     dispatch

x_in:   call    getw
        mov     dx,ax
        in      al,dx
        mov     ah,al
        mov     al,'I'
        call    send2
        jmp     dispatch

x_int10:
        mov     si,regs
        mov     cx,8
.read:  call    getc
        mov     [si],al
        inc     si
        loop    .read
        push    di
        mov     ax,[regs]
        mov     bx,[regs+2]
        mov     cx,[regs+4]
        mov     dx,[regs+6]
        push    bp
        int     10h
        pop     bp
        pop     di
        push    cs
        pop     ds
        cld
        mov     byte [mode_set],1
        call    video_segment
        push    ax
        mov     ah,al
        mov     al,'V'
        call    send2
        pop     ax
        mov     al,'v'
        call    send2
        jmp     dispatch

x_sound:
        call    getw
        or      ax,ax
        jz      .quiet
        mov     cx,ax
        mov     al,0B6h                 ; timer 2, a square wave
        out     43h,al
        mov     al,cl
        out     42h,al
        mov     al,ch
        out     42h,al
        in      al,61h
        or      al,3
        out     61h,al
        jmp     dispatch
.quiet: call    speaker_off
        jmp     dispatch

x_baud: call    getw
        or      ax,ax
        jmpif   z, bad_op
        mov     cx,ax
        mov     ah,al
        mov     al,'B'
        call    send2
        call    drain
        mov     ax,cx
        call    set_divisor
        mov     byte [trial],1
        mov     byte [idling],0
        jmp     dispatch

x_end:  call    getc
        mov     ah,al
        mov     al,'A'
        call    send2
        cmp     byte [trial],0
        je      .done
        mov     byte [trial],0          ; the new speed works: keep it
        mov     ax,[divisor]
        mov     [good_divisor],ax
.done:  jmp     dispatch

x_hello:
        call    hello
        jmp     dispatch

x_quit: mov     ax,'Q'                  ; ('Q', 0)
        call    send2
        jmp     finish

x_leave:
        call    getc
        mov     [exit_code],al
        jmp     x_quit

; D4: a batch file for DOS to run, then back to DOS to run it.
x_run:  call    getw
        mov     cx,ax
        mov     dx,ax                   ; DX: how many (getc keeps it)
        xor     si,si
        jcxz    .no
.read:  call    getc
        cmp     si,RUNMAX
        jae     .over                   ; (too long: read the rest away, then say no)
        mov     [runbuf+si],al
        inc     si
.over:  loop    .read
        cmp     dx,RUNMAX
        ja      .no
        call    quiet_errors
        mov     dx,run_name
        xor     cx,cx
        mov     ah,3Ch                  ; create (or empty) it
        int     21h
        jc      .shut
        mov     bx,ax
        mov     dx,runbuf
        mov     cx,si
        mov     ah,40h
        int     21h
        pushf
        push    ax
        mov     ah,3Eh
        int     21h
        pop     ax
        popf
        jc      .shut
        cmp     ax,si                   ; (a full disk writes less)
        jne     .shut
        call    loud_errors
        mov     byte [exit_code],RUN_EXIT
        jmp     x_quit
.shut:  call    loud_errors
.no:    mov     ax,'E'+100h             ; ('E', 1)
        call    send2
        jmp     dispatch

; D5: is there a file of that name?
x_there:
        call    getw
        mov     cx,ax
        xor     si,si
        jcxz    .ask
.read:  call    getc
        cmp     si,127
        jae     .over
        mov     [runbuf+si],al
        inc     si
.over:  loop    .read
.ask:   mov     byte [runbuf+si],0
        call    quiet_errors
        mov     dx,runbuf
        mov     cx,27h                  ; read-only, hidden, system and archived files too
        mov     ah,4Eh                  ; (into the DTA: the command line's old place)
        int     21h
        mov     ax,'F'+100h             ; ('F', 1)
        jnc     .say
        mov     ah,0                    ; ('F', 0)
.say:   push    ax
        call    loud_errors
        pop     ax
        call    send2
        jmp     dispatch

; While PILINK asks DOS about files: a disk error (no disk in A:, say) fails
; the call instead of asking "Abort, Retry, Fail?", which would wait for a
; key the BIOS never hears. ES is the screen's: kept.
quiet_errors:
        push    es
        push    bx
        mov     ax,3524h
        int     21h
        mov     [old_i24],bx
        mov     [old_i24+2],es
        mov     dx,fail_i24
        mov     ax,2524h
        int     21h
        pop     bx
        pop     es
        ret
loud_errors:
        push    ds
        push    dx
        lds     dx,[old_i24]
        mov     ax,2524h
        int     21h
        pop     dx
        pop     ds
        ret
fail_i24:
        mov     al,3                    ; "fail"
        iret

x_chars:
        call    getc
        mov     dl,al                   ; DL: the attribute
        call    getc
        lostcheck
        xor     ch,ch
        mov     cl,al
        jcxz    .done
.each:  call    getc
        mov     ah,dl
        stosw
        loop    .each
.done:  jmp     dispatch

; ------------------------------------------------------------ when it goes wrong

bad_op: mov     byte [rxerr],20h

; Bytes were lost or wrong: tell the Pi, then wait for a quiet line.
line_error:
        mov     sp,[base_sp]
        cmp     byte [trial],0
        jmpif   ne, trial_failed
        mov     al,'N'
        mov     ah,[rxerr]
        call    send2
resync: mov     word [patience],0
.again: mov     byte [rxerr],0
        cli
        mov     ax,[rhead]
        mov     [rtail],ax
        sti
        call    ticks
        mov     [idle_from],ax
.wait:  call    txpump
        cmp     byte [quit],0
        jmpif   ne, local_quit
        mov     ax,[rhead]
        cmp     ax,[rtail]
        je      .still
        inc     word [patience]         ; (a line that never goes quiet: give up
        cmp     word [patience],4000    ; after a few thousand tries, about a minute)
        jmpif   a, gone_quiet
        jmp     .again
.still: call    ticks
        sub     ax,[idle_from]
        cmp     ax,QUIET_TICKS
        jb      .wait
        mov     byte [rxerr],0
        mov     byte [idling],0
        mov     ax,'R'                  ; ('R', 0): ready again
        call    send2
        mov     word [emit],emit_11
        mov     byte [hshift],0
        jmp     dispatch

; A command stopped halfway and nothing more came.
starved:
        mov     byte [rxerr],1
        jmp     line_error
; A new speed didn't work out: back to the last one that did.
trial_failed:
        mov     sp,[base_sp]
        mov     byte [trial],0
        mov     ax,[good_divisor]
        call    set_divisor
        call    hello
        jmp     resync

local_quit:
        mov     sp,[base_sp]
        mov     byte [exit_code],1
        mov     ax,'Q'+100h             ; ('Q', 1)
        call    send2
        jmp     finish

; The Pi has said nothing for 15 seconds.
gone_quiet:
        mov     sp,[base_sp]
        test    byte [flags],2          ; started by Kermit: back to it
        jnz     .leave
        cmp     byte [linked],0         ; never linked: just keep saying hello
        je      .wait
        mov     ax,[start_divisor]      ; by ourselves: wait for the Pi again,
        call    set_divisor             ; at the speed we started at
        mov     [good_divisor],ax
        call    speaker_off
        cmp     byte [mode_set],0
        je      .text
        xor     ah,ah
        mov     al,[old_mode]
        int     10h
        push    cs
        pop     ds
        cld
        call    video_segment
        mov     byte [mode_set],0
.text:  call    banner
        mov     byte [linked],0
        mov     byte [trial],0
.wait:  call    hello
        jmp     resync
.leave: mov     byte [exit_code],2
        mov     ax,'Q'+200h             ; ('Q', 2)
        call    send2

finish: call    drain
        call    give_back
        mov     al,[exit_code]
        mov     ah,4Ch
        int     21h

; ------------------------------------------------------------ receiving

; The next byte from the Pi, in AL, waiting for it. Uses BX.
getc:   mov     bx,[rtail]
.wait:  cmp     bx,[rhead]
        jne     .have
        call    idle
        jmp     .wait
.have:  mov     al,[rbuf+bx]
        inc     bx
        and     bx,RSIZE-1
        mov     [rtail],bx
        mov     byte [idling],0
        ret

; The next word, in AX. Uses BX.
getw:   call    getc
        push    ax
        call    getc
        mov     ah,al
        pop     bx
        mov     al,bl
        ret

; Nothing to read: send what's waiting, and watch the clock. Changes no
; registers. (Its ways out, when things have gone wrong, don't return.)
idle:   push    ax
        push    bx
        push    dx
        cmp     byte [held],0           ; we'd asked the Pi to wait: carry on
        je      .pump
        mov     dx,[p_mcr]
        mov     al,0Bh
        out     dx,al
        mov     byte [held],0
.pump:  call    txpump
        cmp     byte [quit],0
        jmpif   ne, local_quit
        test    byte [rxerr],0FFh
        jmpif   nz, line_error
        call    ticks
        cmp     byte [idling],0
        jne     .timing
        mov     byte [idling],1
        mov     [idle_from],ax
        jmp     .out
.timing:
        sub     ax,[idle_from]
        cmp     byte [incmd],0
        je      .between
        cmp     ax,STARVE_TICKS
        jmpif   ae, starved
        jmp     .out
.between:
        cmp     byte [trial],0
        je      .linked
        cmp     ax,TRIAL_TICKS
        jmpif   ae, trial_failed
        jmp     .out
.linked:
        cmp     byte [linked],0
        jne     .watch
        cmp     ax,HELLO_TICKS          ; nobody has answered yet: hello again
        jb      .out
        test    byte [flags],2
        jz      .again
        inc     byte [hellos]           ; (Kermit started us and the Pi isn't
        cmp     byte [hellos],8         ; there: back to Kermit after 15 s)
        jmpif   ae, gone_quiet
.again: call    hello
        mov     byte [idling],0
        jmp     .out
.watch: cmp     ax,SILENCE_TICKS
        jmpif   ae, gone_quiet
.out:   pop     dx
        pop     bx
        pop     ax
        ret

; The serial port has something for us (IRQ 4, or 3 for COM2).
com_isr:
        push    ax
        push    bx
        push    dx
        push    ds
        push    cs
        pop     ds
.more:  mov     dx,[p_lsr]
        in      al,dx
        mov     ah,al
        and     ah,1Eh                  ; overrun, parity, framing, break
        or      [rxerr],ah
        test    al,1
        jz      .done
        mov     dx,[p_data]
        in      al,dx
        mov     bx,[rhead]
        mov     [rbuf+bx],al
        inc     bx
        and     bx,RSIZE-1
        cmp     bx,[rtail]
        je      .full
        mov     [rhead],bx
        sub     bx,[rtail]              ; three quarters full: ask the Pi to
        and     bx,RSIZE-1              ; wait (RTS off), if the cable carries it
        cmp     bx,RSIZE/4*3
        jb      .more
        cmp     byte [held],0
        jne     .more
        mov     dx,[p_mcr]
        mov     al,09h
        out     dx,al
        mov     byte [held],1
        jmp     .more
.full:  or      byte [rxerr],80h
        jmp     .more
.done:  mov     al,[eoi]
        out     20h,al
        pop     ds
        pop     dx
        pop     bx
        pop     ax
        iret

; ------------------------------------------------------------ the keyboard

; A key went down or up (IRQ 1). The BIOS never hears of it: the scancode
; goes to the Pi as it is.
kbd_isr:
        push    ax
        push    bx
        push    ds
        push    cs
        pop     ds
        in      al,60h
        mov     ah,al
        cmp     al,1Dh                  ; Ctrl
        jne     .1
        or      byte [kshift],1
        jmp     .keep
.1:     cmp     al,9Dh
        jne     .2
        and     byte [kshift],0FEh
        jmp     .keep
.2:     cmp     al,38h                  ; Alt
        jne     .3
        or      byte [kshift],2
        jmp     .keep
.3:     cmp     al,0B8h
        jne     .4
        and     byte [kshift],0FDh
        jmp     .keep
.4:     cmp     al,53h                  ; Del
        je      .both
        cmp     al,01h                  ; Esc
        jne     .keep
.both:  cmp     byte [kshift],3
        jne     .keep
        mov     byte [quit],1
.keep:  mov     bx,[khead]
        mov     [kbuf+bx],ah
        inc     bx
        and     bx,KSIZE-1
        cmp     bx,[ktail]
        je      .full
        mov     [khead],bx
.full:  mov     al,61h                  ; that's IRQ 1 dealt with
        out     20h,al
        pop     ds
        pop     bx
        pop     ax
        iret

; ------------------------------------------------------------ sending

; Sends the two bytes AL then AH (queued: txpump puts them on the line).
send2:  call    tput
        xchg    al,ah
        call    tput
        xchg    al,ah
        ret

tput:   push    bx
.again: mov     bx,[thead]
        mov     [tbuf+bx],al
        inc     bx
        and     bx,TSIZE-1
        cmp     bx,[ttail]
        jne     .ok
        call    txpump                  ; (full: make room)
        jmp     .again
.ok:    mov     [thead],bx
        pop     bx
        ret

; Keys waiting become 'K' messages; then one byte goes out, if the serial
; chip is ready for it. Changes no registers.
txpump: push    ax
        push    bx
        push    dx
.keys:  mov     bx,[ktail]
        cmp     bx,[khead]
        je      .send
        mov     ax,[thead]              ; (only with room for both bytes)
        sub     ax,[ttail]
        and     ax,TSIZE-1
        cmp     ax,TSIZE-3
        ja      .send
        mov     ah,[kbuf+bx]
        inc     bx
        and     bx,KSIZE-1
        mov     [ktail],bx
        mov     al,'K'
        call    send2
        jmp     .keys
.send:  mov     bx,[ttail]
        cmp     bx,[thead]
        je      .done
        mov     dx,[p_lsr]
        cli                             ; (reading this clears the error bits,
        in      al,dx                   ; so they're kept here too)
        mov     ah,al
        and     ah,1Eh
        or      [rxerr],ah
        sti
        test    al,20h
        jz      .done
        mov     al,[tbuf+bx]
        mov     dx,[p_data]
        out     dx,al
        inc     bx
        and     bx,TSIZE-1
        mov     [ttail],bx
.done:  pop     dx
        pop     bx
        pop     ax
        ret

; Waits until everything queued has left the serial chip (a second at most).
drain:  push    ax
        push    bx
        push    dx
        call    ticks
        mov     bx,ax
.wait:  call    txpump
        call    ticks
        sub     ax,bx
        cmp     ax,18
        jae     .done
        mov     ax,[thead]
        cmp     ax,[ttail]
        jne     .wait
        mov     dx,[p_lsr]
        cli
        in      al,dx
        mov     ah,al
        and     ah,1Eh
        or      [rxerr],ah
        sti
        test    al,40h
        jz      .wait
.done:  pop     dx
        pop     bx
        pop     ax
        ret

; ESC _ P L version flags mode ESC \ : who we are.
hello:  push    ax
        mov     ax,5F1Bh                ; ESC _
        call    send2
        mov     ax,'PL'
        call    send2
        mov     al,VERSION+20h
        mov     ah,[flags]
        add     ah,20h
        call    send2
        call    video_mode
        add     al,20h
        mov     ah,1Bh
        call    send2
        mov     al,'\'
        call    tput
        pop     ax
        ret

; ------------------------------------------------------------ dots, widened

emit_11:
        stosb
        ret
emit_12:
        mov     [es:di+2000h],al
        stosb
        ret
emit_21:
        mov     bl,al
        xor     bh,bh
        shl     bx,1
        mov     ax,[wide+bx]
        stosw
        ret
emit_22:
        mov     bl,al
        xor     bh,bh
        shl     bx,1
        mov     ax,[wide+bx]
        mov     [es:di+2000h],ax
        stosw
        ret
emit_41:
        mov     bl,al
        xor     bh,bh
        shl     bx,1
        mov     si,[wide+bx]
        mov     bx,si
        xor     bh,bh
        shl     bx,1
        mov     ax,[wide+bx]
        stosw
        mov     bx,si
        mov     bl,bh
        xor     bh,bh
        shl     bx,1
        mov     ax,[wide+bx]
        stosw
        ret
emit_42:
        mov     bl,al
        xor     bh,bh
        shl     bx,1
        mov     si,[wide+bx]
        mov     bx,si
        xor     bh,bh
        shl     bx,1
        mov     ax,[wide+bx]
        mov     [es:di+2000h],ax
        stosw
        mov     bx,si
        mov     bl,bh
        xor     bh,bh
        shl     bx,1
        mov     ax,[wide+bx]
        mov     [es:di+2000h],ax
        stosw
        ret

; wide[b]: byte b with every dot doubled, as two bytes, the left one first.
make_tables:
        xor     bx,bx
.next:  mov     al,bl
        shr     al,4
        call    .spread
        mov     dl,al
        mov     al,bl
        and     al,0Fh
        call    .spread
        mov     dh,al
        mov     si,bx
        shl     si,1
        mov     [wide+si],dx
        inc     bl
        jnz     .next
        ret
.spread:
        mov     cx,4                    ; AL's low four bits, each doubled
        mov     ah,al
        shl     ah,4
        xor     al,al
.bit:   shl     al,2
        shl     ah,1
        jnc     .zero
        or      al,3
.zero:  loop    .bit
        ret

; ------------------------------------------------------------ small things

; The BIOS's clock, in AX: it ticks 18.2 times a second.
ticks:  push    ds
        mov     ax,40h
        mov     ds,ax
        mov     ax,[6Ch]
        pop     ds
        ret

; The video mode now, in AL. Uses AH, BX.
video_mode:
        push    di
        push    bp
        mov     ah,0Fh
        int     10h
        pop     bp
        pop     di
        push    cs
        pop     ds
        cld
        ret

video_segment:
        push    ax
        mov     ax,0B800h
        mov     es,ax
        pop     ax
        ret

speaker_off:
        push    ax
        in      al,61h
        and     al,0FCh
        out     61h,al
        pop     ax
        ret

; The serial chip's speed: 115200 divided by AX. Keeps AX.
set_divisor:
        push    dx
        push    ax
        mov     [divisor],ax
        mov     dx,[p_lcr]
        cli
        mov     al,83h                  ; (the divisor's two bytes, then 8N1)
        out     dx,al
        pop     ax
        push    ax
        mov     dx,[p_data]
        out     dx,al
        inc     dx
        mov     al,ah
        out     dx,al
        mov     dx,[p_lcr]
        mov     al,03h
        out     dx,al
        mov     ax,[rhead]              ; (what arrived at the old speed is no use)
        mov     [rtail],ax
        sti
        pop     ax
        pop     dx
        ret

banner: cmp     byte [mode_set],0       ; (only on a text screen we haven't touched,
        jne     .done                   ; or one we've just put back)
        mov     dx,waiting
        mov     ah,9
        int     21h
.done:  ret

; ------------------------------------------------------------ starting, stopping

arguments:
        mov     si,81h
.next:  lodsb
        cmp     al,0Dh
        je      .done
        cmp     al,'/'
        je      .switch
        cmp     al,'0'
        jb      .next
        cmp     al,'9'
        ja      .next
        xor     bx,bx                   ; a number: the divisor
.digit: sub     al,'0'
        xor     ah,ah
        push    ax
        mov     ax,10
        mul     bx
        mov     bx,ax
        pop     ax
        add     bx,ax
        lodsb
        cmp     al,'0'
        jb      .number
        cmp     al,'9'
        jbe     .digit
.number:
        mov     [start_divisor],bx
        dec     si
        jmp     .next
.switch:
        lodsb
        cmp     al,0Dh
        je      .done
        and     al,0DFh                 ; (upper case)
        cmp     al,'K'
        jne     .n
        or      byte [flags],2
.n:     cmp     al,'N'
        jne     .two
        mov     byte [no_fifo],1
.two:   cmp     al,'2' & 0DFh
        jne     .next
        mov     byte [com],1
        jmp     .next
.done:  ret

; Where the serial port is, from the BIOS's own list.
find_port:
        push    es
        mov     ax,40h
        mov     es,ax
        xor     bx,bx
        mov     bl,[com]
        shl     bx,1
        mov     ax,[es:bx]
        pop     es
        or      ax,ax
        jnz     .known
        mov     ax,3F8h
        cmp     byte [com],0
        je      .known
        mov     ax,2F8h
.known: mov     [p_data],ax
        add     ax,3
        mov     [p_lcr],ax
        inc     ax
        mov     [p_mcr],ax
        inc     ax
        mov     [p_lsr],ax
        mov     byte [irq],4            ; ports at 3F8 and 3E8 use IRQ 4; 2F8 and
        test    word [p_data],100h      ; 2E8 use IRQ 3 (the Compaq's one port
        jnz     .done                   ; can be jumpered to either)
        mov     byte [irq],3
.done:  mov     al,[irq]
        or      al,60h                  ; "that's this IRQ dealt with"
        mov     [eoi],al
        ret

; Takes the serial port and the keyboard, remembering how they were.
take_over:
        mov     dx,[p_lcr]              ; the port as Kermit (or the BIOS) left it
        in      al,dx
        mov     [old_lcr],al
        or      al,80h
        cli
        out     dx,al
        mov     dx,[p_data]
        in      al,dx
        mov     ah,al
        inc     dx
        in      al,dx
        xchg    al,ah
        mov     [old_divisor],ax
        mov     dx,[p_lcr]
        mov     al,[old_lcr]
        out     dx,al
        sti
        mov     dx,[p_data]
        inc     dx
        in      al,dx
        mov     [old_ier],al
        mov     dx,[p_mcr]
        in      al,dx
        mov     [old_mcr],al
        mov     dx,[p_data]
        add     dx,2
        in      al,dx                   ; was its buffer (FIFO) in use?
        and     al,0C0h
        mov     [old_fifo],al

        mov     al,0C7h                 ; has it a buffer at all? (a 16550A)
        out     dx,al
        in      al,dx
        and     al,0C0h
        cmp     al,0C0h
        jne     .plain
        cmp     byte [no_fifo],0
        jne     .plain
        mov     al,87h                  ; on, emptied, tell us at 8 bytes
        out     dx,al
        or      byte [flags],1
        jmp     .vectors
.plain: xor     al,al
        out     dx,al

.vectors:
        mov     al,[irq]
        add     al,8
        mov     [com_int],al
        mov     ah,35h
        int     21h
        mov     [old_com],bx
        mov     [old_com+2],es
        mov     ax,3509h
        int     21h
        mov     [old_kbd],bx
        mov     [old_kbd+2],es
        mov     ah,0Fh
        int     10h
        mov     [old_mode],al
        call    video_segment
        xor     di,di

        cmp     word [start_divisor],0
        jne     .speed
        mov     word [start_divisor],12 ; 9600
        test    byte [flags],2
        jz      .speed
        mov     ax,[old_divisor]        ; (from Kermit: as it is)
        mov     [start_divisor],ax
.speed: mov     ax,[start_divisor]
        mov     [good_divisor],ax
        call    set_divisor             ; (and 8 bits, no parity, 1 stop)

        mov     al,[com_int]
        mov     ah,25h
        mov     dx,com_isr
        int     21h
        mov     ax,2509h
        mov     dx,kbd_isr
        int     21h

        cli
        mov     dx,[p_mcr]
        mov     al,0Bh                  ; DTR, RTS, and interrupts through (OUT2)
        out     dx,al
        mov     dx,[p_data]
        in      al,dx                   ; (anything stale)
        mov     dx,[p_lsr]
        in      al,dx
        mov     dx,[p_data]
        inc     dx
        mov     al,01h                  ; tell us when a byte arrives
        out     dx,al
        in      al,21h
        mov     [old_mask],al
        mov     cl,[irq]
        mov     ah,1
        shl     ah,cl
        not     ah
        and     al,ah
        out     21h,al
        mov     al,[irq]                ; the serial port first in line, ahead of
        dec     al                      ; the clock and keyboard: at 115200 a byte
        or      al,0C0h                 ; waits only 87 millionths of a second
        out     20h,al
        sti
        ret

; Puts everything back as it was.
give_back:
        cli
        mov     dx,[p_data]
        inc     dx
        mov     al,[old_ier]
        out     dx,al
        inc     dx
        xor     al,al
        cmp     byte [old_fifo],0C0h
        jne     .fifo
        mov     al,81h
.fifo:  out     dx,al
        mov     al,0C7h                 ; IRQ order as usual
        out     20h,al
        in      al,21h
        mov     cl,[irq]
        mov     ah,1
        shl     ah,cl
        mov     bl,[old_mask]
        and     bl,ah
        not     ah
        and     al,ah
        or      al,bl
        out     21h,al
        sti
        mov     ax,[old_divisor]
        call    set_divisor
        mov     dx,[p_lcr]
        mov     al,[old_lcr]
        out     dx,al
        mov     dx,[p_mcr]
        mov     al,[old_mcr]
        out     dx,al
        push    ds
        mov     al,[com_int]
        mov     ah,25h
        lds     dx,[old_com]
        int     21h
        pop     ds
        push    ds
        mov     ax,2509h
        lds     dx,[old_kbd]
        int     21h
        pop     ds
        push    ds                      ; the BIOS missed every key since we
        mov     ax,40h                  ; started: no Shift, Ctrl or Alt held,
        mov     ds,ax                   ; nothing waiting
        and     byte [17h],0F0h
        mov     byte [18h],0
        cli
        mov     ax,[1Ah]
        mov     [1Ch],ax
        sti
        pop     ds
        call    speaker_off
        cmp     byte [mode_set],0
        je      .done
        xor     ah,ah
        mov     al,[old_mode]
        int     10h
.done:  ret

; ------------------------------------------------------------ data

ext_table:
        dw      x_nop, x_seek, x_litw, x_fillw, x_back, x_copy, x_scale, x_sink
        dw      x_mode, x_cursor, x_out, x_in, x_int10, x_sound, x_baud, x_end
        dw      x_hello, x_quit, x_leave, x_chars, x_run, x_there
emitters:
        dw      emit_11, emit_12, emit_21, emit_22, emit_41, emit_42
emit    dw      emit_11
waiting db      'PILINK 3: waiting for the Raspberry Pi. (Ctrl+Alt+Esc leaves.)', 13, 10, '$'
start_divisor   dw 0
run_name db     'C:\PI\PIRUN.BAT', 0
exit_code db    0
flags   db      0
no_fifo db      0
com     db      0
hshift  db      0
incmd   db      0
idling  db      0
linked  db      0
hellos  db      0
trial   db      0
quit    db      0
held    db      0
rxerr   db      0
kshift  db      0
mode_set db     0
rhead   dw      0
rtail   dw      0
khead   dw      0
ktail   dw      0
thead   dw      0
ttail   dw      0

section .bss
base_sp         resw 1
idle_from       resw 1
patience        resw 1
divisor         resw 1
good_divisor    resw 1
old_divisor     resw 1
old_com         resd 1
old_i24         resd 1
old_kbd         resd 1
p_data          resw 1
p_lcr           resw 1
p_mcr           resw 1
p_lsr           resw 1
regs            resw 4
irq             resb 1
eoi             resb 1
com_int         resb 1
old_lcr         resb 1
old_ier         resb 1
old_mcr         resb 1
old_fifo        resb 1
old_mask        resb 1
old_mode        resb 1
kbuf            resb KSIZE
tbuf            resb TSIZE
wide            resw 256
rbuf            resb RSIZE
runbuf          resb RUNMAX
