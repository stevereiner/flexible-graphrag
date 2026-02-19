# Source Path Examples

This document provides detailed examples for configuring `SOURCE_PATHS` in Flexible GraphRAG across different operating systems and scenarios.

## 📁 **Basic Syntax**

```bash
SOURCE_PATHS=["path1", "path2", "path3"]
```

The `SOURCE_PATHS` configuration accepts a JSON array of strings, where each string can be:
- A single file path
- A directory path (processes ALL files in the directory)
- Mixed files and directories

## 🪟 **Windows Examples**

### **Single File**
```bash
# Using forward slashes (recommended)
SOURCE_PATHS=["C:/Documents/report.pdf"]

# Using backslashes (escape required)
SOURCE_PATHS=["C:\\Documents\\report.pdf"]

# Windows "Copy as path" format (paste directly!)
SOURCE_PATHS=["C:\Users\John Doe\Documents\My Report.pdf"]
```

### **Multiple Files**
```bash
SOURCE_PATHS=["C:/file1.pdf", "D:/folder/file2.docx", "E:/data/file3.txt"]

# With spaces in paths
SOURCE_PATHS=["C:\1 sample files\cmispress.pdf", "D:\My Files\reports\annual.docx"]
```

### **Whole Directory**
```bash
# Processes ALL files in the directory
SOURCE_PATHS=["C:/Documents/reports"]

# Multiple directories
SOURCE_PATHS=["C:/Documents/reports", "D:/Projects/data", "E:/Archive"]
```

### **Mixed Files and Directories**
```bash
SOURCE_PATHS=["C:/specific-file.pdf", "C:/Documents/folder", "D:/another-file.docx"]
```

### **Relative Paths (Windows)**
```bash
# Relative to the project root
SOURCE_PATHS=["./sample-docs", "./data/reports"]
SOURCE_PATHS=["..\\parent-folder\\documents"]
```

### **UNC Network Paths**
```bash
# Using forward slashes
SOURCE_PATHS=["//server/share/folder"]

# Using backslashes
SOURCE_PATHS=["\\\\server\\share\\folder"]
```

## 🍎 **macOS Examples**

### **Single File**
```bash
SOURCE_PATHS=["/Users/username/Documents/report.pdf"]
SOURCE_PATHS=["/Applications/MyApp/data/file.txt"]
```

### **Multiple Files**
```bash
SOURCE_PATHS=["/Users/john/Desktop/file1.pdf", "/Users/john/Downloads/file2.docx"]
```

### **Whole Directory**
```bash
SOURCE_PATHS=["/Users/username/Documents/work-files"]
SOURCE_PATHS=["/Volumes/ExternalDrive/data"]
```

### **Relative Paths (macOS)**
```bash
SOURCE_PATHS=["./sample-docs", "../shared-data"]
SOURCE_PATHS=["~/Documents/my-files"]  # Home directory shortcut
```

## 🐧 **Linux Examples**

### **Single File**
```bash
SOURCE_PATHS=["/home/username/documents/report.pdf"]
SOURCE_PATHS=["/opt/data/analysis.txt"]
```

### **Multiple Files**
```bash
SOURCE_PATHS=["/home/user/file1.pdf", "/var/data/file2.csv", "/tmp/temp-file.txt"]
```

### **Whole Directory**
```bash
SOURCE_PATHS=["/home/username/project-data"]
SOURCE_PATHS=["/mnt/shared/documents"]
```

### **Relative Paths (Linux)**
```bash
SOURCE_PATHS=["./local-data", "../shared-folder"]
SOURCE_PATHS=["~/documents/work"]  # Home directory shortcut
```

## ⚠️ **Important Notes**

### **Directory Processing Warning**
When you specify a directory path, the system will process **ALL** files in that directory:
```bash
# This processes EVERY file in the reports directory
SOURCE_PATHS=["C:/Documents/reports"]
```

If you only want specific files, list them individually:
```bash
# This processes only these specific files
SOURCE_PATHS=["C:/Documents/reports/q1.pdf", "C:/Documents/reports/q2.pdf"]
```

### **File Types Supported**
The system supports these file formats:
- **Documents**: PDF, DOCX, PPTX, TXT, MD
- **Spreadsheets**: XLSX, CSV  
- **Web**: HTML
- **Images**: PNG, JPG (with OCR)
- **Archive**: ASCIIDOC

### **Path Encoding**
- **Windows**: Use forward slashes `/` or double backslashes `\\`
- **Spaces**: Paths with spaces are supported, no escaping needed in JSON array
- **Special characters**: Most Unicode characters are supported

## 🖥️ **UI Client Differences**

Different UI clients use different environment variable names:

### **Backend (FastAPI)**
```bash
SOURCE_PATHS=["./sample-docs/file.pdf"]
```

### **Angular Frontend**
```bash
PROCESS_FOLDER_PATH=./sample-docs
```

### **React/Vue Frontends**
```bash
VITE_PROCESS_FOLDER_PATH=./sample-docs
```

**Note**: Frontend environment variables typically expect a single directory path, while the backend `SOURCE_PATHS` accepts multiple files and directories.

## 🗄️ **Repository Path Examples (CMIS/Alfresco)**

### **CMIS Repository Paths**
CMIS uses standard CMIS path format:
```bash
# CMIS paths start with /
CMIS_FOLDER_PATH=/Shared/Documents
CMIS_FOLDER_PATH=/Sites/my-site/documentLibrary/folder
```

### **Alfresco Repository Paths**
**NEW (python-alfresco-api 1.1.5+)**: Alfresco now uses **native Alfresco paths** with flexible format:

```bash
# Short format (recommended - matches what you see in Alfresco Share)
ALFRESCO_PATH=/Shared/GraphRAG
ALFRESCO_PATH=/Sites/my-site/documentLibrary/Reports
ALFRESCO_PATH=/User Homes/admin/My Files

# Full format (also works - system automatically strips /Company Home prefix)
ALFRESCO_PATH=/Company Home/Shared/GraphRAG
ALFRESCO_PATH=/Company Home/Sites/my-site/documentLibrary/Reports
```

**Both formats work!** The system automatically strips `/Company Home` prefix if present, since the root node already represents Company Home.

**Benefits of Native Alfresco Paths:**
- ✅ More intuitive - matches what you see in Alfresco Share UI
- ✅ Consistent with Alfresco Content Services API
- ✅ Works with `relative_path` feature for better performance
- ✅ Flexible - use short format (`/Shared`) or full format (`/Company Home/Shared`)
- ✅ Backward compatible - both formats supported

**Path Examples:**
```bash
# Shared folder (short format - recommended)
/Shared/GraphRAG/documents

# Sites (short format - recommended)
/Sites/engineering/documentLibrary/specs

# User Homes (short format - recommended)
/User Homes/admin/My Files

# Data Dictionary (short format - recommended)
/Data Dictionary/Scripts

# Full format also works (optional)
/Company Home/Shared/GraphRAG/documents
/Company Home/Sites/engineering/documentLibrary/specs
```

## 💡 **Best Practices**

1. **Use relative paths** when possible for portability
2. **Start small** - test with one file before processing large directories
3. **Use forward slashes** on Windows for consistency
4. **Check file permissions** ensure the application can read the specified paths
5. **Avoid system directories** stick to user documents and data folders
6. **Test paths** verify paths exist and are accessible before running
7. **Alfresco paths** - Use native `/Company Home/...` format for clarity (python-alfresco-api 1.1.5+)
