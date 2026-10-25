// SPDX-FileCopyrightText: 2013-2026 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

package net.sourceforge.gemrb;

import org.libsdl.app.SDLActivity;
import android.os.Bundle;
import android.util.Log;
import java.io.IOException;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileInputStream;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.BufferedOutputStream;
import java.io.BufferedInputStream;
import java.io.InputStream;
import android.content.res.AssetManager;
import java.util.Enumeration;
import java.util.zip.*;
import java.util.Properties;
import android.app.AlertDialog;
import android.widget.EditText;
import android.content.DialogInterface;
import android.content.res.Configuration;
import android.os.Environment;

public class GemRB extends SDLActivity {

  public String newPath;

  protected void onCreate(Bundle savedInstanceState) {
    File gemrbHomeFolder = getApplicationContext().getExternalFilesDir(null); // null for general purpose files
    String[] foldersToExtract = { "GUIScripts", "override", "unhardcoded" };

    // first clear the directories and their contents
    Log.d("GemRB Activity", "Cleaning up...");
    for(String folder : foldersToExtract) {
      deleteRecursive(new File(gemrbHomeFolder.getAbsolutePath().concat(gemrbHomeFolder.separator).concat(folder)));
    }

    Log.d("GemRB Activity", "Extracting new files...");
    try {
      extractFolder(this.getApplication().getPackageCodePath(), gemrbHomeFolder.getAbsolutePath());
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
    Log.d("GemRB Activity", "Done.");

    Log.d("GemRB Activity", "Checking GemRB.cfg content.");

    File finalConfFile = new File(gemrbHomeFolder.getAbsolutePath().concat(gemrbHomeFolder.separator).concat("GemRB.cfg"));
    File userSuppliedConfig = new File(Environment.getExternalStorageDirectory().getAbsolutePath().concat(gemrbHomeFolder.separator).concat("GemRB.cfg"));

    if(!finalConfFile.exists()) {
      Log.d("GemRB Activity", "GemRB.cfg doesn't exist in the expected location, creating it from the packaged template.");

      // String[] keysToChange = { "GUIScriptsPath", "GemRBOverridePath", "GemRBUnhardcodedPath" };
      try {
        File inConfFile = new File(gemrbHomeFolder.getAbsolutePath().concat(gemrbHomeFolder.separator).concat("packaged.GemRB.cfg"));
        BufferedReader inConf = new BufferedReader(new FileReader(inConfFile));
        File outConfFile = new File(gemrbHomeFolder.getAbsolutePath().concat(gemrbHomeFolder.separator).concat("new.GemRB.cfg"));
        BufferedWriter outConf = new BufferedWriter(new FileWriter(outConfFile));

        String line;

        while((line = inConf.readLine()) != null) {
          outConf.write(line.concat("\n"));
          outConf.flush();
        }
        inConf.close();
        outConf.flush();
        outConf.close();

        inConfFile.delete();
        outConfFile.renameTo(finalConfFile);
      } catch (IOException e) {
        throw new RuntimeException(e);
      }
    }

    super.onCreate(savedInstanceState);
  }

  private static void deleteRecursive(File fileOrDirectory) {
      if (fileOrDirectory.isDirectory())
          for (File child : fileOrDirectory.listFiles())
              deleteRecursive(child);

      fileOrDirectory.delete();
  }

  private static void extractFolder(String zipFile, String newPath) throws ZipException, IOException {
      File destination = new File(newPath).getCanonicalFile();
      if (!destination.isDirectory() && !destination.mkdirs()) {
          throw new IOException("Cannot create asset extraction directory");
      }
      String destinationPath = destination.getPath() + File.separator;
      String assetPrefix = "assets/";
      byte[] data = new byte[1024 * 1024];

      try (ZipFile zip = new ZipFile(zipFile)) {
          Enumeration<? extends ZipEntry> entries = zip.entries();
          while (entries.hasMoreElements()) {
              ZipEntry entry = entries.nextElement();
              String currentEntry = entry.getName();
              if (!currentEntry.startsWith(assetPrefix)) {
                  continue;
              }
              String relativePath = currentEntry.substring(assetPrefix.length());
              if (relativePath.isEmpty() && entry.isDirectory()) {
                  continue;
              }
              if (new File(relativePath).isAbsolute() || relativePath.indexOf('\\') >= 0) {
                  throw new IOException("Invalid absolute or platform-dependent asset path");
              }
              File destFile = new File(destination, relativePath).getCanonicalFile();
              if (!destFile.getPath().startsWith(destinationPath)) {
                  throw new IOException("Asset entry escapes extraction directory");
              }
              File directory = entry.isDirectory() ? destFile : destFile.getParentFile();
              if (!directory.isDirectory() && !directory.mkdirs()) {
                  throw new IOException("Cannot create asset directory");
              }
              if (!entry.isDirectory()) {
                  try (InputStream input = zip.getInputStream(entry);
                       FileOutputStream output = new FileOutputStream(destFile)) {
                      int count;
                      while ((count = input.read(data)) != -1) {
                          output.write(data, 0, count);
                      }
                  }
              }
          }
      }
  }

  public void onConfigurationChanged(Configuration newConfig) {
    // we're only overriding for orientation change (cmp AndroidManifest.xml)
    // but we don't actually want to react to that
    super.onConfigurationChanged(newConfig);
  }
}
