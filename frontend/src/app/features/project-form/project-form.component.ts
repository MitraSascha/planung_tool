import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { NotificationService } from '../../core/services/notification.service';
import { ProjectService } from '../../core/services/project.service';
import { formatHttpError } from '../../core/services/error-format';
import { ProjectForm, ProjectType } from '../../core/models';

type SmallTemplateKind = 'bathroom' | 'gas_floor' | 'custom';

@Component({
  selector: 'app-project-form',
  imports: [CommonModule, FormsModule],
  templateUrl: './project-form.component.html',
  styleUrl: './project-form.component.scss',
})
export class ProjectFormComponent implements OnInit {
  private readonly projectService = inject(ProjectService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug?: string;

  protected slugTouched = false;

  protected onNameInput(): void {
    if (this.isEditMode || this.slugTouched) {
      return;
    }
    this.form.slug = this.slugify(this.form.name);
  }

  protected onSlugInput(): void {
    this.slugTouched = true;
    // Force the slug to remain valid as the user types
    this.form.slug = this.slugify(this.form.slug);
  }

  private slugify(value: string | undefined | null): string {
    if (!value) return '';
    const replacements: Record<string, string> = {
      'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
      'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue',
      'é': 'e', 'è': 'e', 'ê': 'e',
      'á': 'a', 'à': 'a', 'â': 'a',
      'í': 'i', 'ì': 'i', 'î': 'i',
      'ó': 'o', 'ò': 'o', 'ô': 'o',
      'ú': 'u', 'ù': 'u', 'û': 'u',
    };
    return value
      .toString()
      .replace(/[äöüßÄÖÜéèêáàâíìîóòôúùû]/g, (ch) => replacements[ch] ?? ch)
      .toLowerCase()
      .replace(/[^a-z0-9-]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 63);
  }

  protected readonly smallProjectOutputs = [
    '00_Start',
    '01_Monteur',
    '04_Projektleitung',
    '05_Allgemein',
  ];

  protected isEditMode = false;

  protected form: ProjectForm = this.defaultForm();

  ngOnInit(): void {
    if (this.slug) {
      this.isEditMode = true;
      this.projectService.get(this.slug).subscribe({
        next: (project) => {
          this.form = {
            slug: project.slug,
            name: project.name,
            project_type: project.project_type,
            address: project.address ?? '',
            responsible: project.responsible ?? '',
            construction_manager: project.construction_manager ?? '',
            foreman: project.foreman ?? '',
            planned_start: project.planned_start ?? '',
            planned_end: project.planned_end ?? '',
            notes: project.notes ?? '',
            sections: project.sections.map((section) => ({ ...section })),
          };
        },
        error: (response) =>
          this.notifications.showError(formatHttpError(response, 'Projekt konnte nicht geladen werden.')),
      });
    }
  }

  protected setProjectType(type: ProjectType): void {
    this.form.project_type = type;
  }

  protected addSection(): void {
    this.form.sections.push({
      number: this.form.sections.length + 1,
      name: '',
      goal: '',
      planned_hours: null,
      responsible: '',
      staff: '',
    });
  }

  protected removeSection(index: number): void {
    if (this.form.sections.length === 1) {
      return;
    }
    this.form.sections.splice(index, 1);
    this.form.sections.forEach((section, sectionIndex) => {
      section.number = sectionIndex + 1;
    });
  }

  protected applySmallProjectTemplate(kind: SmallTemplateKind): void {
    this.form.project_type = 'small';

    if (kind === 'bathroom') {
      this.form.name = 'Badsanierung';
      this.form.notes = 'Kleinprojekt: Badezimmer sanieren, Abbruch, Rohinstallation, Feininstallation, Abnahme.';
      this.form.sections = [
        { number: 1, name: 'Vorbereitung und Schutz', goal: 'Baustelle einrichten, Laufwege schuetzen, Bestand dokumentieren.', planned_hours: 8, responsible: '', staff: '' },
        { number: 2, name: 'Demontage und Rohinstallation', goal: 'Altbestand demontieren, Wasser/Abwasser/Heizung vorbereiten.', planned_hours: 24, responsible: '', staff: '' },
        { number: 3, name: 'Endmontage und Abnahme', goal: 'Objekte montieren, Dichtheit pruefen, Tagesbericht und Fotodoku abschliessen.', planned_hours: 16, responsible: '', staff: '' },
      ];
      return;
    }

    if (kind === 'gas_floor') {
      this.form.name = 'Gasetagenheizung';
      this.form.notes = 'Kleinprojekt: einzelne Gasetagenheizung erneuern oder neu bauen.';
      this.form.sections = [
        { number: 1, name: 'Bestand und Absicherung', goal: 'Bestand pruefen, Absperrungen, Schutzmassnahmen und Materialkontrolle.', planned_hours: 6, responsible: '', staff: '' },
        { number: 2, name: 'Montage Heizgeraet und Anschluesse', goal: 'Geraet setzen, Rohrleitungen anschliessen, Abgas/Verbrennungsluft beruecksichtigen.', planned_hours: 18, responsible: '', staff: '' },
        { number: 3, name: 'Pruefung, Inbetriebnahme und Einweisung', goal: 'Dichtheit, Funktion, Dokumentation und Einweisung abschliessen.', planned_hours: 8, responsible: '', staff: '' },
      ];
      return;
    }

    this.form.sections = [
      { number: 1, name: 'Arbeitspaket 1', goal: 'Leistungsumfang und Tagesziel beschreiben.', planned_hours: null, responsible: '', staff: '' },
    ];
  }

  protected submit(): void {
    this.notifications.clear();
    const request$ = this.isEditMode && this.slug
      ? this.projectService.update(this.slug, this.form)
      : this.projectService.create(this.form);
    request$.subscribe({
      next: () => {
        this.notifications.showMessage(
          this.isEditMode
            ? 'Projekt wurde aktualisiert.'
            : 'Projekt wurde angelegt und der Workspace wurde erstellt.',
        );
        this.projectService.list().subscribe();
        this.router.navigate(['/projects', this.form.slug, 'details']);
      },
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Projekt konnte nicht gespeichert werden.'),
        ),
    });
  }

  private defaultForm(): ProjectForm {
    return {
      slug: '',
      name: '',
      project_type: 'standard',
      address: '',
      client_name: '',
      responsible: '',
      construction_manager: '',
      foreman: '',
      planned_start: '',
      planned_end: '',
      notes: '',
      sections: [
        {
          number: 1,
          name: '',
          goal: '',
          planned_hours: undefined,
          responsible: '',
          staff: '',
        },
      ],
    };
  }
}
