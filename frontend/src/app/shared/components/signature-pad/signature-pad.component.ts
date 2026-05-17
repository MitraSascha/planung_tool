import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnDestroy,
  Output,
  ViewChild,
} from '@angular/core';

interface PadPoint {
  x: number;
  y: number;
}

@Component({
  selector: 'app-signature-pad',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './signature-pad.component.html',
  styleUrl: './signature-pad.component.scss',
})
export class SignaturePadComponent implements AfterViewInit, OnDestroy {
  @Input() width = 400;
  @Input() height = 150;
  @Input() label?: string;
  @Input() lineColor = '#17212b';
  @Input() lineWidth = 2;
  @Input() backgroundColor = '#ffffff';

  /** Fires after each stroke with the PNG dataURL; empty string when cleared. */
  @Output() readonly signatureChange = new EventEmitter<string>();

  @ViewChild('canvas', { static: true })
  private canvasRef!: ElementRef<HTMLCanvasElement>;

  private ctx: CanvasRenderingContext2D | null = null;
  private drawing = false;
  private hasContent = false;
  private lastPoint: PadPoint | null = null;
  private dpr = 1;

  ngAfterViewInit(): void {
    const canvas = this.canvasRef.nativeElement;
    this.dpr = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = Math.round(this.width * this.dpr);
    canvas.height = Math.round(this.height * this.dpr);
    canvas.style.width = `${this.width}px`;
    canvas.style.height = `${this.height}px`;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }
    this.ctx = ctx;
    ctx.scale(this.dpr, this.dpr);
    this.paintBackground();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = this.lineColor;
    ctx.lineWidth = this.lineWidth;
  }

  ngOnDestroy(): void {
    this.ctx = null;
  }

  protected onPointerDown(event: PointerEvent): void {
    if (!this.ctx) {
      return;
    }
    event.preventDefault();
    this.drawing = true;
    const point = this.relativePoint(event);
    this.lastPoint = point;
    this.ctx.beginPath();
    this.ctx.moveTo(point.x, point.y);
    // Draw a dot for taps so the stroke is visible immediately.
    this.ctx.lineTo(point.x + 0.01, point.y + 0.01);
    this.ctx.stroke();
    try {
      (event.target as Element).setPointerCapture?.(event.pointerId);
    } catch {
      // ignore capture errors
    }
  }

  protected onPointerMove(event: PointerEvent): void {
    if (!this.drawing || !this.ctx || !this.lastPoint) {
      return;
    }
    event.preventDefault();
    const point = this.relativePoint(event);
    this.ctx.beginPath();
    this.ctx.moveTo(this.lastPoint.x, this.lastPoint.y);
    this.ctx.lineTo(point.x, point.y);
    this.ctx.stroke();
    this.lastPoint = point;
    this.hasContent = true;
  }

  protected onPointerUp(event: PointerEvent): void {
    if (!this.drawing) {
      return;
    }
    this.drawing = false;
    this.lastPoint = null;
    try {
      (event.target as Element).releasePointerCapture?.(event.pointerId);
    } catch {
      // ignore release errors
    }
    if (this.hasContent) {
      this.emitCurrent();
    }
  }

  @HostListener('window:pointerup')
  protected onWindowPointerUp(): void {
    if (this.drawing) {
      this.drawing = false;
      this.lastPoint = null;
      if (this.hasContent) {
        this.emitCurrent();
      }
    }
  }

  protected clear(): void {
    if (!this.ctx) {
      return;
    }
    const canvas = this.canvasRef.nativeElement;
    this.ctx.save();
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.clearRect(0, 0, canvas.width, canvas.height);
    this.ctx.restore();
    this.paintBackground();
    this.hasContent = false;
    this.signatureChange.emit('');
  }

  /** Returns the current signature as PNG data URL, or empty string if blank. */
  toDataUrl(): string {
    if (!this.hasContent) {
      return '';
    }
    return this.canvasRef.nativeElement.toDataURL('image/png');
  }

  private emitCurrent(): void {
    this.signatureChange.emit(this.toDataUrl());
  }

  private paintBackground(): void {
    if (!this.ctx) {
      return;
    }
    this.ctx.save();
    this.ctx.fillStyle = this.backgroundColor;
    this.ctx.fillRect(0, 0, this.width, this.height);
    this.ctx.restore();
  }

  private relativePoint(event: PointerEvent): PadPoint {
    const rect = this.canvasRef.nativeElement.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }
}
