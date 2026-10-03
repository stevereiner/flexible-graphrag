import { Component, EventEmitter, Output, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatSnackBar } from '@angular/material/snack-bar';
import { finalize, switchMap, takeWhile, takeUntil } from 'rxjs/operators';
import { Subject, interval } from 'rxjs';
import { ApiService } from '@flexible-graphrag/angular-ui';
import { EnvService } from '../../services/env.service';
import { AsyncProcessingResponse, ProcessingStatusResponse } from '@flexible-graphrag/angular-ui';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-process-folder',
  templateUrl: './process-folder.component.html',
  styleUrls: ['./process-folder.component.scss'],
  standalone: false
})
export class ProcessFolderComponent implements OnInit, OnDestroy {
  @Output() processed = new EventEmitter<{ dataSource: string, path?: string }>();
  
  form: FormGroup;
  isProcessing = false;
  processingStatus = '';
  environment = environment; // Make environment accessible in template
  processingProgress = 0;
  currentProcessingId: string | null = null;
  statusData: any = null;
  
  // In-window messages instead of popups
  successMessage = '';
  errorMessage = '';
  
  private destroy$ = new Subject<void>();

  constructor(
    private fb: FormBuilder,
    private apiService: ApiService,
    private snackBar: MatSnackBar,
    private envService: EnvService
  ) {
    this.form = this.fb.group({
      dataSource: ['filesystem', Validators.required],
      folderPath: [''],
      // CMIS fields
      cmisUrl: [`${this.envService.cmisBaseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`],
      cmisUsername: ['admin'],
      cmisPassword: ['admin'],
      // Alfresco fields
      alfrescoUrl: [`${this.envService.alfrescoBaseUrl}/alfresco`],
      alfrescoUsername: ['admin'],
      alfrescoPassword: ['admin']
    });

    // Set up conditional validators
    this.form.get('dataSource')?.valueChanges.subscribe(dataSource => {
      this.updateValidators(dataSource);
    });
  }

  ngOnInit(): void {
    // Set default folder path from environment config
    const defaultPath = this.envService.defaultFolderPath;
    if (defaultPath) {
      this.form.patchValue({
        folderPath: defaultPath
      });
    }
    
    // Set initial validators
    this.updateValidators('filesystem');
  }

  private updateValidators(dataSource: string): void {
    // Clear all validators first
    Object.keys(this.form.controls).forEach(key => {
      if (key !== 'dataSource') {
        this.form.get(key)?.clearValidators();
      }
    });

    // Set validators based on data source
    switch (dataSource) {
      case 'filesystem':
        this.form.get('folderPath')?.setValidators([Validators.required]);
        break;
      case 'cmis':
        this.form.get('cmisUrl')?.setValidators([Validators.required]);
        this.form.get('cmisUsername')?.setValidators([Validators.required]);
        this.form.get('cmisPassword')?.setValidators([Validators.required]);
        this.form.get('folderPath')?.setValidators([Validators.required]);
        break;
      case 'alfresco':
        this.form.get('alfrescoUrl')?.setValidators([Validators.required]);
        this.form.get('alfrescoUsername')?.setValidators([Validators.required]);
        this.form.get('alfrescoPassword')?.setValidators([Validators.required]);
        this.form.get('folderPath')?.setValidators([Validators.required]);
        break;
    }

    // Update validity
    Object.keys(this.form.controls).forEach(key => {
      this.form.get(key)?.updateValueAndValidity();
    });
  }

  onSubmit(): void {
    if (this.form.invalid || this.isProcessing) {
      return;
    }

    this.isProcessing = true;
    const formValue = this.form.value;
    
    // Build request based on data source
    const request: any = {
      data_source: formValue.dataSource
    };

    if (formValue.dataSource === 'filesystem') {
      request.paths = [formValue.folderPath];
    } else if (formValue.dataSource === 'cmis') {
      // For now, we'll pass the paths as the folder path since CMIS isn't fully implemented
      request.paths = [formValue.folderPath];
      // In future, these would be used to configure CMIS connection
      request.cmis_config = {
        url: formValue.cmisUrl,
        username: formValue.cmisUsername,
        password: formValue.cmisPassword,
        folder_path: formValue.folderPath
      };
    } else if (formValue.dataSource === 'alfresco') {
      // For now, we'll pass the paths as the folder path since Alfresco isn't fully implemented
      request.paths = [formValue.folderPath];
      // In future, these would be used to configure Alfresco connection
      request.alfresco_config = {
        url: formValue.alfrescoUrl,
        username: formValue.alfrescoUsername,
        password: formValue.alfrescoPassword,
        path: formValue.folderPath
      };
    }

    this.apiService.ingestDocuments(request)
      .subscribe({
        next: (response: AsyncProcessingResponse) => {
          if (response.status === 'started') {
            this.processingStatus = response.message;
            this.processingProgress = 0;
            this.currentProcessingId = response.processing_id;
            
            // Show success message in-window instead of popup
            this.successMessage = `Processing started: ${response.estimated_time || 'Please wait...'}`;
            this.errorMessage = '';
            
            this.pollProcessingStatus(response.processing_id, formValue);
          } else if (response.status === 'completed') {
            this.handleProcessingComplete(formValue);
          } else if (response.status === 'failed') {
            this.handleProcessingError(response.error || 'Processing failed');
          }
        },
        error: (error) => {
          this.handleProcessingError(error.message || 'Error starting document processing');
        }
      });
  }

  private pollProcessingStatus(processingId: string, formValue: any): void {
    // Poll every 2 seconds
    interval(2000)
      .pipe(
        switchMap(() => this.apiService.getProcessingStatus(processingId)),
        takeWhile((status: ProcessingStatusResponse) => 
          status.status === 'started' || status.status === 'processing', true
        ),
        takeUntil(this.destroy$)
      )
      .subscribe({
        next: (status: ProcessingStatusResponse) => {
          this.processingStatus = status.message;
          this.processingProgress = status.progress;
          this.statusData = status;  // Store full status for enhanced progress display
          
          // Clear initial "processing started" message once real progress updates begin
          if (this.successMessage.startsWith('Processing started:') && status.progress > 0) {
            this.successMessage = '';
          }
          
          if (status.status === 'completed') {
            this.handleProcessingComplete(formValue, status.message);
          } else if (status.status === 'failed') {
            this.handleProcessingError(status.error || 'Processing failed');
          } else if (status.status === 'cancelled') {
            this.handleProcessingCancelled();
          }
        },
        error: (error: any) => {
          this.handleProcessingError('Error checking processing status: ' + error.message);
        }
      });
  }

  private handleProcessingComplete(formValue: any, completionMessage?: string): void {
    this.isProcessing = false;
    this.processingStatus = '';
    this.processingProgress = 0;
    this.currentProcessingId = null;
    
    // Show backend's completion message (more accurate than generic message)
    this.successMessage = completionMessage || 'Documents ingested successfully!';
    this.errorMessage = '';
    
    this.processed.emit({ 
      dataSource: formValue.dataSource, 
      path: formValue.folderPath 
    });
  }

  private handleProcessingError(errorMessage: string): void {
    this.isProcessing = false;
    this.processingStatus = '';
    this.processingProgress = 0;
    this.currentProcessingId = null;
    
    // Show error message in-window instead of popup
    this.errorMessage = errorMessage;
    this.successMessage = '';
  }

  private handleProcessingCancelled(): void {
    this.isProcessing = false;
    this.processingStatus = '';
    this.processingProgress = 0;
    this.currentProcessingId = null;
    
    // Show cancellation message in-window with auto-clear
    this.successMessage = 'Processing cancelled successfully';
    this.errorMessage = '';
    
    // Auto-clear the cancellation message after 5 seconds
    setTimeout(() => {
      if (this.successMessage === 'Processing cancelled successfully') {
        this.successMessage = '';
      }
    }, 5000);
  }

  cancelProcessing(): void {
    if (!this.currentProcessingId) return;
    
    this.apiService.cancelProcessing(this.currentProcessingId).subscribe({
      next: (response: any) => {
        if (response.success) {
          // Success will be handled by the polling status check
        } else {
          this.errorMessage = 'Failed to cancel processing';
          this.successMessage = '';
        }
      },
      error: (error: any) => {
        console.error('Error cancelling processing:', error);
        this.errorMessage = 'Error cancelling processing';
        this.successMessage = '';
      }
    });
  }

  getFileName(filePath: string): string {
    return filePath.split(/[/\\]/).pop() || filePath;
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
