/*-
 * Copyright (c) 2014 Red Hat, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.fedoraproject.copr.client.cli;

import com.beust.jcommander.JCommander;
import com.beust.jcommander.Parameter;
import com.beust.jcommander.ParameterException;
import org.fedoraproject.copr.client.CoprConfiguration;
import org.fedoraproject.copr.client.CoprException;
import org.fedoraproject.copr.client.CoprSession;
import org.fedoraproject.copr.client.impl.DefaultCoprService;

/**
 * @author Mikolaj Izdebski
 */
public class CoprCli
{
    @Parameter( names = { "-h", "--help" }, description = "Show generic help", help = true )
    private boolean help;

    @Parameter( names = { "--help-commands" }, description = "Show help about subcommands" )
    private boolean helpCommands;

    @Parameter( names = { "-c", "--config" }, description = "Select configuration file to use" )
    private String configPath;

    public void run( String[] args )
    {
        JCommander jc = new JCommander( this );
        ConfigurationLoader loader = new ConfigurationLoader();
        CoprConfiguration configuration = loader.loadConfiguration( configPath );
        if ( configuration == null )
        {
            System.err.println( "Unable to load Copr configuration" );
            System.exit( 1 );
        }
        jc.addCommand( "list", new ListCommand() );
        try
        {
            jc.parse( args );
            try (CoprSession session = new DefaultCoprService().newSession( configuration ))
            {
                JCommander commander = jc.getCommands().get( jc.getParsedCommand() );
                CliCommand command = (CliCommand) commander.getObjects().get( 0 );
                command.run( session );
            }
        }
        catch ( CoprException | ParameterException e )
        {
            System.err.println( e.getLocalizedMessage() );
            System.exit( 1 );
        }
    }
}
