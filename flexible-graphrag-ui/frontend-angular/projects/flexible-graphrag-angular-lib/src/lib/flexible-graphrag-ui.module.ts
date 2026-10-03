import { ModuleWithProviders, NgModule, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatListModule } from '@angular/material/list';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';
import { MatToolbarModule } from '@angular/material/toolbar';
import { TextFieldModule } from '@angular/cdk/text-field';

import { SourcesTabComponent } from './components/sources-tab/sources-tab';
import { ProcessingTabComponent } from './components/processing-tab/processing-tab';
import { SearchTabComponent } from './components/search-tab/search-tab';
import { ChatTabComponent } from './components/chat-tab/chat-tab';
import {
  BaseSourceFormComponent,
  FileUploadFormComponent,
  WebSourceFormComponent,
  WikipediaSourceFormComponent,
  YouTubeSourceFormComponent,
  CMISSourceFormComponent,
  AlfrescoSourceFormComponent,
  NuxeoSourceFormComponent,
  S3SourceFormComponent,
  GCSSourceFormComponent,
  AzureBlobSourceFormComponent,
  OneDriveSourceFormComponent,
  SharePointSourceFormComponent,
  BoxSourceFormComponent,
  GoogleDriveSourceFormComponent
} from './components/sources';
import { FLEXIBLE_GRAPHRAG_CONFIG, FlexibleGraphragConfig } from './flexible-graphrag.config';

const COMPONENTS = [
  SourcesTabComponent,
  ProcessingTabComponent,
  SearchTabComponent,
  ChatTabComponent,
  BaseSourceFormComponent,
  FileUploadFormComponent,
  WebSourceFormComponent,
  WikipediaSourceFormComponent,
  YouTubeSourceFormComponent,
  CMISSourceFormComponent,
  AlfrescoSourceFormComponent,
  NuxeoSourceFormComponent,
  S3SourceFormComponent,
  GCSSourceFormComponent,
  AzureBlobSourceFormComponent,
  OneDriveSourceFormComponent,
  SharePointSourceFormComponent,
  BoxSourceFormComponent,
  GoogleDriveSourceFormComponent
];

/**
 * The four Flexible GraphRAG tabs and their source forms, shared by the standalone Angular
 * app and by host applications such as an Alfresco Content App extension.
 *
 * HttpClient is deliberately NOT provided here: the host owns it, so an ACA extension keeps
 * ADF's interceptors (which attach the Alfresco ticket) on every request this library makes.
 */
@NgModule({
  declarations: [...COMPONENTS],
  imports: [
    CommonModule, FormsModule, ReactiveFormsModule,
    MatButtonModule, MatCardModule, MatCheckboxModule, MatChipsModule, MatDividerModule,
    MatFormFieldModule, MatIconModule, MatInputModule, MatListModule, MatMenuModule,
    MatProgressBarModule, MatProgressSpinnerModule, MatSelectModule, MatSlideToggleModule,
    MatSnackBarModule, MatTableModule, MatTabsModule, MatToolbarModule, TextFieldModule
  ],
  exports: [...COMPONENTS],
  schemas: [CUSTOM_ELEMENTS_SCHEMA]
})
export class FlexibleGraphragUiModule {
  /** Register the module and supply the host's configuration in one call. */
  static forRoot(config: FlexibleGraphragConfig): ModuleWithProviders<FlexibleGraphragUiModule> {
    return {
      ngModule: FlexibleGraphragUiModule,
      providers: [{ provide: FLEXIBLE_GRAPHRAG_CONFIG, useValue: config }]
    };
  }
}
