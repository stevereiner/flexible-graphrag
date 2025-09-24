import { NgModule, APP_INITIALIZER, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { HttpClientModule } from '@angular/common/http';
import { ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableModule } from '@angular/material/table';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatListModule } from '@angular/material/list';
import { MatDividerModule } from '@angular/material/divider';
import { MatMenuModule } from '@angular/material/menu';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { TextFieldModule } from '@angular/cdk/text-field';
import { CommonModule } from '@angular/common';
import { firstValueFrom } from 'rxjs';

import { AppComponent } from './app.component';
import { ProcessFolderComponent } from './components/process-folder/process-folder.component';
import { QueryFormComponent } from './components/query-form/query-form.component';
import { EnvService } from './services/env.service';
import { SourcesTabComponent } from './components/sources-tab/sources-tab';
import { ProcessingTabComponent } from './components/processing-tab/processing-tab';
import { SearchTabComponent } from './components/search-tab/search-tab';
import { ChatTabComponent } from './components/chat-tab/chat-tab';

// Import all source form components
import { 
  BaseSourceFormComponent,
  FileUploadFormComponent,
  WebSourceFormComponent,
  WikipediaSourceFormComponent,
  YouTubeSourceFormComponent,
  CMISSourceFormComponent,
  AlfrescoSourceFormComponent,
  S3SourceFormComponent,
  GCSSourceFormComponent,
  AzureBlobSourceFormComponent,
  OneDriveSourceFormComponent,
  SharePointSourceFormComponent,
  BoxSourceFormComponent,
  GoogleDriveSourceFormComponent
} from './components/sources';

// Factory function to initialize environment configuration
export function initializeEnv(envService: EnvService) {
  return () => firstValueFrom(envService.loadEnvConfig());
}

@NgModule({
  declarations: [
    AppComponent,
    ProcessFolderComponent,
    QueryFormComponent,
    SourcesTabComponent,
    ProcessingTabComponent,
    SearchTabComponent,
    ChatTabComponent,
    // Add all source form components
    BaseSourceFormComponent,
    FileUploadFormComponent,
    WebSourceFormComponent,
    WikipediaSourceFormComponent,
    YouTubeSourceFormComponent,
    CMISSourceFormComponent,
    AlfrescoSourceFormComponent,
    S3SourceFormComponent,
    GCSSourceFormComponent,
    AzureBlobSourceFormComponent,
    OneDriveSourceFormComponent,
    SharePointSourceFormComponent,
    BoxSourceFormComponent,
    GoogleDriveSourceFormComponent
  ],
  imports: [
    BrowserModule,
    CommonModule,
    BrowserAnimationsModule,
    HttpClientModule,
    ReactiveFormsModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatProgressBarModule,
    MatSnackBarModule,
    MatToolbarModule,
    MatIconModule,
    MatSelectModule,
    MatTabsModule,
    MatTableModule,
    MatCheckboxModule,
    MatChipsModule,
    MatListModule,
    MatDividerModule,
    MatMenuModule,
    MatSlideToggleModule,
    TextFieldModule
  ],
  providers: [
    EnvService,
    {
      provide: APP_INITIALIZER,
      useFactory: initializeEnv,
      deps: [EnvService],
      multi: true
    }
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  bootstrap: [AppComponent]
})
export class AppModule { }
