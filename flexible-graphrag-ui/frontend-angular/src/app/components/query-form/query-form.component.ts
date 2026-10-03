import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatSnackBar } from '@angular/material/snack-bar';
import { finalize } from 'rxjs/operators';
import { ApiService } from '@flexible-graphrag/angular-ui';
import { ApiResponse, SearchResult } from '@flexible-graphrag/angular-ui';

@Component({
  selector: 'app-query-form',
  templateUrl: './query-form.component.html',
  styleUrls: ['./query-form.component.scss'],
  standalone: false
})
export class QueryFormComponent {
  form: FormGroup;
  isQuerying = false;
  answer: string | null = null;
  searchResults: SearchResult[] | null = null;

  constructor(
    private fb: FormBuilder,
    private apiService: ApiService,
    private snackBar: MatSnackBar
  ) {
    this.form = this.fb.group({
      question: ['', Validators.required],
      searchMode: ['search', Validators.required]  // Default to search
    });
  }

  onSubmit(): void {
    if (this.form.invalid || this.isQuerying) {
      return;
    }

    const request = {
      query: this.form.value.question,
      top_k: 10
    };

    const searchMode = this.form.value.searchMode;
    console.log('Submitting request:', request, 'Mode:', searchMode);
    
    this.isQuerying = true;
    this.answer = null;
    this.searchResults = null;
    
    const apiCall = searchMode === 'search' 
      ? this.apiService.search(request)
      : this.apiService.query(request);
    
    apiCall.pipe(
        finalize(() => this.isQuerying = false)
      )
      .subscribe({
        next: (response: ApiResponse) => {
          console.log('Response received:', response);
          
          if (searchMode === 'search') {
            // Handle search results
            if (response.results && response.results.length > 0) {
              this.searchResults = response.results;
            } else {
              this.snackBar.open('No search results found', 'Close', { duration: 3000 });
            }
          } else {
            // Handle Q&A response
            if (response.answer) {
              this.answer = response.answer;
            } else {
              this.answer = 'No answer found';
            }
          }
          
          console.log('Final result:', { answer: this.answer, searchResults: this.searchResults });
        },
        error: (error) => {
          console.error('Query error:', error);
          this.snackBar.open(
            error.message || `Error executing ${searchMode}`,
            'Close',
            { duration: 5000, panelClass: ['error-snackbar'] }
          );
        }
      });
  }

  onClear(): void {
    this.answer = null;
    this.searchResults = null;
    this.form.reset();
    // Reset to default values
    this.form.patchValue({
      searchMode: 'search'
    });
  }
}
