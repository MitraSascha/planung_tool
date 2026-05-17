import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
  signal,
} from '@angular/core';

export type AnnotationTool = 'arrow' | 'line' | 'rect' | 'text';

interface Point {
  x: number;
  y: number;
}

interface AnnotationBase {
  tool: AnnotationTool;
  color: string;
  width: number;
}

interface ShapeAnnotation extends AnnotationBase {
  tool: 'arrow' | 'line' | 'rect';
  from: Point;
  to: Point;
}

interface TextAnnotation extends AnnotationBase {
  tool: 'text';
  at: Point;
  text: string;
  fontSize: number;
}

type Annotation = ShapeAnnotation | TextAnnotation;

@Component({
  selector: 'app-photo-annotator',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './photo-annotator.component.html',
  styleUrl: './photo-annotator.component.scss',
})
export class PhotoAnnotatorComponent implements AfterViewInit, OnChanges, OnDestroy {
  /** Source image URL to annotate. */
  @Input() imageUrl = '';
  /** Maximum display width in CSS pixels (image is auto-scaled to fit). */
  @Input() maxWidth = 720;
  /** Maximum display height in CSS pixels. */
  @Input() maxHeight = 540;
  /** Stroke color used for new annotations. */
  @Input() color = '#e53935';
  /** Default stroke width (px). */
  @Input() strokeWidth = 3;

  /** Emits the composited PNG (original + annotation flattened) when "save" is clicked. */
  @Output() readonly annotationSaved = new EventEmitter<Blob>();
  /** Emits when the user cancels (closes the annotator without saving). */
  @Output() readonly cancelled = new EventEmitter<void>();

  @ViewChild('imageCanvas', { static: true })
  private imageCanvasRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('overlayCanvas', { static: true })
  private overlayCanvasRef!: ElementRef<HTMLCanvasElement>;

  protected readonly tool = signal<AnnotationTool>('arrow');
  protected readonly loading = signal(true);
  protected readonly hasContent = signal(false);
  protected readonly errorText = signal<string | null>(null);

  private annotations: Annotation[] = [];
  private drawing = false;
  private currentStart: Point | null = null;
  private currentEnd: Point | null = null;
  private displayWidth = 0;
  private displayHeight = 0;
  private naturalWidth = 0;
  private naturalHeight = 0;
  private dpr = 1;
  private image: HTMLImageElement | null = null;

  ngAfterViewInit(): void {
    this.dpr = Math.max(1, window.devicePixelRatio || 1);
    if (this.imageUrl) {
      this.loadImage();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['imageUrl'] && !changes['imageUrl'].firstChange && this.imageUrl) {
      this.annotations = [];
      this.hasContent.set(false);
      this.loadImage();
    }
  }

  ngOnDestroy(): void {
    this.image = null;
  }

  protected selectTool(tool: AnnotationTool): void {
    this.tool.set(tool);
  }

  protected clearAnnotations(): void {
    this.annotations = [];
    this.hasContent.set(false);
    this.redrawOverlay();
  }

  protected undoLast(): void {
    if (this.annotations.length === 0) {
      return;
    }
    this.annotations.pop();
    this.hasContent.set(this.annotations.length > 0);
    this.redrawOverlay();
  }

  protected save(): void {
    if (!this.image) {
      return;
    }
    const composite = document.createElement('canvas');
    composite.width = this.naturalWidth;
    composite.height = this.naturalHeight;
    const ctx = composite.getContext('2d');
    if (!ctx) {
      return;
    }
    ctx.drawImage(this.image, 0, 0, this.naturalWidth, this.naturalHeight);

    const scale = this.naturalWidth / this.displayWidth;
    ctx.save();
    ctx.scale(scale, scale);
    this.drawAnnotations(ctx, this.annotations);
    ctx.restore();

    composite.toBlob((blob) => {
      if (blob) {
        this.annotationSaved.emit(blob);
      }
    }, 'image/png');
  }

  protected cancel(): void {
    this.cancelled.emit();
  }

  protected onPointerDown(event: PointerEvent): void {
    if (this.loading()) {
      return;
    }
    event.preventDefault();
    const point = this.relativePoint(event);

    if (this.tool() === 'text') {
      const text = window.prompt('Text fuer Beschriftung eingeben:');
      if (text && text.trim().length > 0) {
        this.annotations.push({
          tool: 'text',
          at: point,
          text: text.trim(),
          color: this.color,
          width: this.strokeWidth,
          fontSize: 18,
        });
        this.hasContent.set(true);
        this.redrawOverlay();
      }
      return;
    }

    this.drawing = true;
    this.currentStart = point;
    this.currentEnd = point;
    try {
      (event.target as Element).setPointerCapture?.(event.pointerId);
    } catch {
      // ignore
    }
  }

  protected onPointerMove(event: PointerEvent): void {
    if (!this.drawing || !this.currentStart) {
      return;
    }
    event.preventDefault();
    this.currentEnd = this.relativePoint(event);
    this.redrawOverlay();
  }

  protected onPointerUp(event: PointerEvent): void {
    if (!this.drawing || !this.currentStart || !this.currentEnd) {
      this.drawing = false;
      this.currentStart = null;
      this.currentEnd = null;
      return;
    }
    event.preventDefault();
    const tool = this.tool();
    if (tool === 'arrow' || tool === 'line' || tool === 'rect') {
      const dx = this.currentEnd.x - this.currentStart.x;
      const dy = this.currentEnd.y - this.currentStart.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist >= 2) {
        this.annotations.push({
          tool,
          from: this.currentStart,
          to: this.currentEnd,
          color: this.color,
          width: this.strokeWidth,
        });
        this.hasContent.set(true);
      }
    }
    this.drawing = false;
    this.currentStart = null;
    this.currentEnd = null;
    try {
      (event.target as Element).releasePointerCapture?.(event.pointerId);
    } catch {
      // ignore
    }
    this.redrawOverlay();
  }

  @HostListener('window:pointerup')
  protected onWindowPointerUp(): void {
    if (this.drawing) {
      this.drawing = false;
      this.currentStart = null;
      this.currentEnd = null;
      this.redrawOverlay();
    }
  }

  private loadImage(): void {
    this.loading.set(true);
    this.errorText.set(null);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      this.image = img;
      this.naturalWidth = img.naturalWidth || img.width;
      this.naturalHeight = img.naturalHeight || img.height;
      const scale = Math.min(
        this.maxWidth / this.naturalWidth,
        this.maxHeight / this.naturalHeight,
        1,
      );
      this.displayWidth = Math.max(50, Math.round(this.naturalWidth * scale));
      this.displayHeight = Math.max(50, Math.round(this.naturalHeight * scale));
      this.setupCanvases();
      this.loading.set(false);
    };
    img.onerror = () => {
      this.loading.set(false);
      this.errorText.set('Bild konnte nicht geladen werden.');
    };
    img.src = this.imageUrl;
  }

  private setupCanvases(): void {
    const imageCanvas = this.imageCanvasRef.nativeElement;
    const overlayCanvas = this.overlayCanvasRef.nativeElement;
    for (const canvas of [imageCanvas, overlayCanvas]) {
      canvas.width = Math.round(this.displayWidth * this.dpr);
      canvas.height = Math.round(this.displayHeight * this.dpr);
      canvas.style.width = `${this.displayWidth}px`;
      canvas.style.height = `${this.displayHeight}px`;
    }
    const imageCtx = imageCanvas.getContext('2d');
    if (imageCtx && this.image) {
      imageCtx.save();
      imageCtx.setTransform(1, 0, 0, 1, 0, 0);
      imageCtx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
      imageCtx.scale(this.dpr, this.dpr);
      imageCtx.drawImage(this.image, 0, 0, this.displayWidth, this.displayHeight);
      imageCtx.restore();
    }
    this.redrawOverlay();
  }

  private redrawOverlay(): void {
    const canvas = this.overlayCanvasRef.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.scale(this.dpr, this.dpr);

    this.drawAnnotations(ctx, this.annotations);

    if (this.drawing && this.currentStart && this.currentEnd) {
      const tool = this.tool();
      if (tool === 'arrow' || tool === 'line' || tool === 'rect') {
        this.drawAnnotation(ctx, {
          tool,
          from: this.currentStart,
          to: this.currentEnd,
          color: this.color,
          width: this.strokeWidth,
        } as ShapeAnnotation);
      }
    }
    ctx.restore();
  }

  private drawAnnotations(
    ctx: CanvasRenderingContext2D,
    annotations: readonly Annotation[],
  ): void {
    for (const annotation of annotations) {
      this.drawAnnotation(ctx, annotation);
    }
  }

  private drawAnnotation(ctx: CanvasRenderingContext2D, annotation: Annotation): void {
    ctx.save();
    ctx.strokeStyle = annotation.color;
    ctx.fillStyle = annotation.color;
    ctx.lineWidth = annotation.width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    if (annotation.tool === 'line') {
      ctx.beginPath();
      ctx.moveTo(annotation.from.x, annotation.from.y);
      ctx.lineTo(annotation.to.x, annotation.to.y);
      ctx.stroke();
    } else if (annotation.tool === 'arrow') {
      this.drawArrow(ctx, annotation.from, annotation.to, annotation.width);
    } else if (annotation.tool === 'rect') {
      const x = Math.min(annotation.from.x, annotation.to.x);
      const y = Math.min(annotation.from.y, annotation.to.y);
      const w = Math.abs(annotation.to.x - annotation.from.x);
      const h = Math.abs(annotation.to.y - annotation.from.y);
      ctx.strokeRect(x, y, w, h);
    } else if (annotation.tool === 'text') {
      ctx.font = `${annotation.fontSize}px "DejaVu Sans", Arial, sans-serif`;
      ctx.textBaseline = 'top';
      const metrics = ctx.measureText(annotation.text);
      const padding = 4;
      const boxX = annotation.at.x - padding;
      const boxY = annotation.at.y - padding;
      const boxW = metrics.width + padding * 2;
      const boxH = annotation.fontSize + padding * 2;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
      ctx.fillRect(boxX, boxY, boxW, boxH);
      ctx.strokeStyle = annotation.color;
      ctx.lineWidth = 1;
      ctx.strokeRect(boxX, boxY, boxW, boxH);
      ctx.fillStyle = annotation.color;
      ctx.fillText(annotation.text, annotation.at.x, annotation.at.y);
    }
    ctx.restore();
  }

  private drawArrow(
    ctx: CanvasRenderingContext2D,
    from: Point,
    to: Point,
    width: number,
  ): void {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const angle = Math.atan2(dy, dx);
    const headLength = Math.max(12, width * 4);
    const headAngle = Math.PI / 7;

    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(to.x, to.y);
    ctx.lineTo(
      to.x - headLength * Math.cos(angle - headAngle),
      to.y - headLength * Math.sin(angle - headAngle),
    );
    ctx.lineTo(
      to.x - headLength * Math.cos(angle + headAngle),
      to.y - headLength * Math.sin(angle + headAngle),
    );
    ctx.closePath();
    ctx.fill();
  }

  private relativePoint(event: PointerEvent): Point {
    const rect = this.overlayCanvasRef.nativeElement.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }
}
